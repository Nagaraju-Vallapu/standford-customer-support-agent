from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .agent import (
	HindsightMemoryService,
	IntegrationError,
	SupportAgent,
	has_explicit_resolution_confirmation,
	redact_card_numbers,
)
from .config import settings
from .database import Database
from .models import (
	ChatRequest,
	ChatResponse,
	ErrorResponse,
	ResolutionMemoryCandidate,
	TicketCreateRequest,
	TicketResponse,
	TicketUpdateRequest,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("standford.backend")
database = Database(settings.database_url)


class ApiError(Exception):
	def __init__(self, status_code: int, message: str) -> None:
		super().__init__(message)
		self.status_code = status_code
		self.message = message


@asynccontextmanager
async def lifespan(app: FastAPI):
	database.initialize()
	async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
		app.state.hindsight = HindsightMemoryService(settings, client)
		app.state.agent = SupportAgent(settings, client)
		yield


app = FastAPI(
	title="Team Standford Support Agent API",
	version="1.0.0",
	description="Memory-driven customer support backed by SQLite, an LLM provider, and Hindsight.",
	lifespan=lifespan,
)

app.add_middleware(
	CORSMiddleware,
	allow_origins=list(settings.cors_origins),
	allow_credentials=False,
	allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
	allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(ApiError)
async def api_error_handler(_request: Request, error: ApiError) -> JSONResponse:
	body = ErrorResponse(message=error.message, code=error.status_code)
	return JSONResponse(status_code=error.status_code, content=body.model_dump())


@app.exception_handler(IntegrationError)
async def integration_error_handler(_request: Request, error: IntegrationError) -> JSONResponse:
	body = ErrorResponse(message=str(error), code=error.status_code)
	return JSONResponse(status_code=error.status_code, content=body.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, error: RequestValidationError) -> JSONResponse:
	issues = []
	for item in error.errors():
		location = ".".join(str(part) for part in item.get("loc", ()) if part not in {"body", "query", "path"})
		description = item.get("msg", "Invalid value")
		issues.append(f"{location}: {description}" if location else description)
	message = "Request validation failed: " + "; ".join(issues)
	body = ErrorResponse(message=message, code=422)
	return JSONResponse(status_code=422, content=body.model_dump())


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_request: Request, error: StarletteHTTPException) -> JSONResponse:
	detail = error.detail if isinstance(error.detail, str) else "The requested resource was not found."
	body = ErrorResponse(message=detail, code=error.status_code)
	return JSONResponse(status_code=error.status_code, content=body.model_dump())


@app.exception_handler(Exception)
async def unexpected_error_handler(_request: Request, error: Exception) -> JSONResponse:
	logger.exception("Unhandled backend error", exc_info=error)
	body = ErrorResponse(message="An unexpected server error occurred.", code=500)
	return JSONResponse(status_code=500, content=body.model_dump())


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
	customer_id = payload.customer_id
	customer_message = redact_card_numbers(payload.message)
	database.ensure_customer(customer_id)
	conversation = database.get_or_create_conversation(customer_id)
	history = database.recent_messages(conversation["conversation_id"])

	hindsight: HindsightMemoryService = request.app.state.hindsight
	agent: SupportAgent = request.app.state.agent
	bank_id, memories = await hindsight.recall(customer_id, customer_message)
	agent_output, _provider = await agent.respond(customer_message, history, memories)

	exchange = database.record_exchange(
		conversation["conversation_id"],
		customer_message,
		agent_output.response,
	)
	memory_status = "recalled" if memories else "not_stored"
	memory_error: str | None = None
	candidate = agent_output.memory_candidate
	previous_customer_message = next((item for item in reversed(history) if item["role"] == "customer"), None)
	previous_assistant_message = next((item for item in reversed(history) if item["role"] == "assistant"), None)

	if (
		candidate
		and previous_customer_message
		and previous_assistant_message
		and has_explicit_resolution_confirmation(customer_message)
	):
		verified_candidate = ResolutionMemoryCandidate(
			issue=redact_card_numbers(previous_customer_message["content"][:500]),
			successful_troubleshooting=redact_card_numbers(previous_assistant_message["content"][:1000]),
			verified_outcome=customer_message[:500],
		)
		document_id = f"resolution-{conversation['conversation_id']}-{exchange['customer_message_id']}"
		try:
			stored_bank_id, summary, category = await hindsight.retain_verified_resolution(
				customer_id,
				conversation["conversation_id"],
				document_id,
				verified_candidate,
			)
			database.add_memory_reference(
				customer_id=customer_id,
				conversation_id=conversation["conversation_id"],
				hindsight_bank_id=stored_bank_id,
				hindsight_document_id=document_id,
				category=category,
				summary=summary,
				metadata={"source": "verified-support-resolution"},
			)
			memory_status = "stored"
		except IntegrationError as error:
			memory_status = "not_stored"
			memory_error = f"The reply was generated, but Hindsight could not store the verified resolution: {error}"
			logger.warning("Verified resolution memory could not be retained for a customer bank")

	return ChatResponse(
		response=agent_output.response,
		conversation_id=conversation["conversation_id"],
		memories=memories,
		status=conversation["status"],
		created_at=exchange["created_at"],
		memory_status=memory_status,
		memory_error=memory_error,
	)


@app.get("/customers/{customer_id}/memories")
async def customer_memories(customer_id: str, request: Request) -> dict[str, list[dict[str, Any]]]:
	customer_id = customer_id.strip()
	if not customer_id or len(customer_id) > 128:
		raise ApiError(422, "customer_id must contain between 1 and 128 characters.")
	database.ensure_customer(customer_id)
	hindsight: HindsightMemoryService = request.app.state.hindsight
	_bank_id, memories = await hindsight.recall(
		customer_id,
		"Customer preferences, prior support issues, troubleshooting attempts, verified resolutions, and important constraints.",
	)
	return {"memories": [memory.model_dump(mode="json", exclude_none=True) for memory in memories]}


@app.post("/tickets", response_model=TicketResponse, status_code=201)
async def create_ticket(payload: TicketCreateRequest) -> dict[str, Any]:
	database.ensure_customer(payload.customer_id)
	subject = redact_card_numbers(payload.subject)
	ticket = database.create_ticket(payload.customer_id, subject)
	return ticket


@app.patch("/tickets/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
	payload: TicketUpdateRequest,
	ticket_id: str = Path(min_length=1, max_length=64),
) -> dict[str, Any]:
	updated = database.update_ticket_status(ticket_id, payload.status)
	if updated is None:
		raise ApiError(404, f"Ticket '{ticket_id}' was not found.")
	return updated
