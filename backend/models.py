from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


TicketStatus = Literal["open", "in_progress", "resolved", "escalated"]
MemoryType = Literal["world", "experience", "observation"]


class ApiModel(BaseModel):
	model_config = ConfigDict(extra="forbid")


class ChatRequest(ApiModel):
	customer_id: str = Field(min_length=1, max_length=128)
	message: str = Field(min_length=1, max_length=20_000)

	@field_validator("customer_id", "message")
	@classmethod
	def strip_required_text(cls, value: str) -> str:
		value = value.strip()
		if not value:
			raise ValueError("must not be blank")
		return value


class TicketCreateRequest(ApiModel):
	customer_id: str = Field(min_length=1, max_length=128)
	subject: str = Field(min_length=1, max_length=500)

	@field_validator("customer_id", "subject")
	@classmethod
	def strip_required_text(cls, value: str) -> str:
		value = value.strip()
		if not value:
			raise ValueError("must not be blank")
		return value


class TicketUpdateRequest(ApiModel):
	status: TicketStatus


class CustomerRegistrationRequest(ApiModel):
	name: str = Field(min_length=1, max_length=200)
	email: str = Field(min_length=3, max_length=254)
	password: str = Field(min_length=8, max_length=1024)

	@field_validator("name")
	@classmethod
	def strip_customer_name(cls, value: str) -> str:
		value = value.strip()
		if not value:
			raise ValueError("must not be blank")
		return value

	@field_validator("email")
	@classmethod
	def normalize_email(cls, value: str) -> str:
		value = value.strip().lower()
		if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
			raise ValueError("must be a valid email address")
		return value


class CustomerLoginRequest(ApiModel):
	email: str = Field(min_length=3, max_length=254)
	password: str = Field(min_length=1, max_length=1024)

	@field_validator("email")
	@classmethod
	def normalize_email(cls, value: str) -> str:
		value = value.strip().lower()
		if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
			raise ValueError("must be a valid email address")
		return value


class CustomerProfileUpdateRequest(ApiModel):
	name: str = Field(min_length=1, max_length=200)
	email: str = Field(min_length=3, max_length=254)

	@field_validator("name")
	@classmethod
	def strip_customer_name(cls, value: str) -> str:
		value = value.strip()
		if not value:
			raise ValueError("must not be blank")
		return value

	@field_validator("email")
	@classmethod
	def normalize_email(cls, value: str) -> str:
		value = value.strip().lower()
		if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
			raise ValueError("must be a valid email address")
		return value


class CustomerProfileResponse(BaseModel):
	customer_id: str
	name: str
	email: str


class AuthResponse(BaseModel):
	access_token: str
	token_type: Literal["bearer"] = "bearer"
	expires_at: datetime
	customer: CustomerProfileResponse


class MemoryResponse(BaseModel):
	model_config = ConfigDict(extra="ignore")

	id: str | None = None
	content: str
	type: MemoryType | None = None
	category: str | None = None
	created_at: datetime | None = None
	relevance_score: float | None = None
	metadata: dict[str, str] | None = None
	successful_solution: str | None = None
	relevance_reason: str | None = None


class ChatResponse(BaseModel):
	response: str
	conversation_id: str
	memories: list[MemoryResponse]
	status: str
	created_at: datetime
	memory_status: Literal["recalled", "stored", "not_stored"]
	memory_error: str | None = None


class TicketResponse(BaseModel):
	ticket_id: str
	customer_id: str
	conversation_id: str | None = None
	subject: str
	status: TicketStatus
	created_at: datetime
	updated_at: datetime


class ErrorResponse(BaseModel):
	error: Literal[True] = True
	message: str
	code: int


class ResolutionMemoryCandidate(BaseModel):
	issue: str = Field(min_length=1, max_length=500)
	successful_troubleshooting: str = Field(min_length=1, max_length=1000)
	verified_outcome: str = Field(min_length=1, max_length=500)


class AgentOutput(BaseModel):
	response: str = Field(min_length=1, max_length=10_000)
	memory_candidate: ResolutionMemoryCandidate | None = None
