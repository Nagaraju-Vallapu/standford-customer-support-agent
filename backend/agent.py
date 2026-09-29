from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from .config import Settings
from .models import AgentOutput, MemoryResponse, ResolutionMemoryCandidate


class IntegrationError(RuntimeError):
	def __init__(self, message: str, status_code: int = 503) -> None:
		super().__init__(message)
		self.status_code = status_code


_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_RESOLUTION_NEGATIVE = re.compile(
	r"\b(?:didn['’]?t work|doesn['’]?t work|not working|still (?:broken|failing|fails|doesn['’]?t work)|"
	r"not (?:fixed|resolved|working)|didn['’]?t help|no change|same problem)\b",
	re.IGNORECASE,
)
_RESOLUTION_POSITIVE = re.compile(
	r"\b(?:that worked|it worked|this worked|that fixed it|it is fixed|it['’]?s fixed|fixed now|"
	r"issue is resolved|problem (?:is )?solved|resolved now|working now|works now|payment went through|"
	r"that solved it|all good now|that helped)\b",
	re.IGNORECASE,
)


def _passes_luhn(value: str) -> bool:
	digits = [int(character) for character in value if character.isdigit()]
	if not 13 <= len(digits) <= 19:
		return False
	checksum = 0
	parity = len(digits) % 2
	for index, digit in enumerate(digits):
		if index % 2 == parity:
			digit *= 2
			if digit > 9:
				digit -= 9
		checksum += digit
	return checksum % 10 == 0


def redact_card_numbers(text: str) -> str:
	def replace(match: re.Match[str]) -> str:
		candidate = match.group(0)
		return "[REDACTED CARD NUMBER]" if _passes_luhn(candidate) else candidate

	return _CARD_CANDIDATE.sub(replace, text)


def has_explicit_resolution_confirmation(message: str) -> bool:
	if _RESOLUTION_NEGATIVE.search(message):
		return False
	return bool(_RESOLUTION_POSITIVE.search(message))


def _utc_now() -> str:
	return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class HindsightMemoryService:
	def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
		self.settings = settings
		self.client = client
		self._ready_banks: set[str] = set()

	@property
	def configured(self) -> bool:
		return bool(self.settings.hindsight_api_url)

	def bank_id_for_customer(self, customer_id: str) -> str:
		digest = hashlib.sha256(customer_id.encode("utf-8")).hexdigest()[:32]
		prefix = re.sub(r"[^a-z0-9-]+", "-", self.settings.hindsight_bank_prefix.lower()).strip("-")
		return f"{prefix or 'standford'}-{digest}"

	def _headers(self) -> dict[str, str]:
		if self.settings.hindsight_api_key:
			return {"Authorization": f"Bearer {self.settings.hindsight_api_key}"}
		return {}

	async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
		if not self.settings.hindsight_api_url:
			raise IntegrationError(
				"Hindsight is not configured. Set HINDSIGHT_API_URL to enable memory recall and storage."
			)

		url = f"{self.settings.hindsight_api_url}/v1/default{path}"
		try:
			response = await self.client.request(method, url, headers=self._headers(), json=payload)
		except httpx.RequestError as error:
			raise IntegrationError(
				"The Hindsight memory service could not be reached. Check HINDSIGHT_API_URL and the Hindsight server."
			) from error

		if not response.is_success:
			if response.status_code in (401, 403):
				detail = "Hindsight rejected the configured credentials. Check HINDSIGHT_API_KEY."
			elif response.status_code == 404:
				detail = "Hindsight could not find the requested memory bank."
			else:
				detail = f"Hindsight returned HTTP {response.status_code}. Check its service configuration and logs."
			raise IntegrationError(detail, 503)

		try:
			data = response.json()
		except ValueError as error:
			raise IntegrationError("Hindsight returned an invalid response.", 502) from error
		if not isinstance(data, dict):
			raise IntegrationError("Hindsight returned an invalid response.", 502)
		return data

	async def ensure_bank(self, customer_id: str) -> str:
		bank_id = self.bank_id_for_customer(customer_id)
		if bank_id in self._ready_banks:
			return bank_id
		await self._request(
			"PUT",
			f"/banks/{quote(bank_id, safe='')}",
			{
				"name": "Standford customer support memory",
				"reflect_mission": (
					"Help a customer-support agent use only relevant, evidence-grounded customer context. "
					"Prioritize verified issues, troubleshooting outcomes, preferences, and constraints. "
					"Do not infer sensitive payment credentials."
				),
				"retain_mission": (
					"Extract durable customer preferences, recurring issues, and verified support resolutions. "
					"Ignore chit-chat and temporary glitches. Never retain card numbers or credentials."
				),
			},
		)
		self._ready_banks.add(bank_id)
		return bank_id

	async def recall(self, customer_id: str, query: str) -> tuple[str, list[MemoryResponse]]:
		bank_id = await self.ensure_bank(customer_id)
		data = await self._request(
			"POST",
			f"/banks/{quote(bank_id, safe='')}/memories/recall",
			{
				"query": query,
				"types": ["world", "experience", "observation"],
				"budget": "low",
				"max_tokens": 2048,
			},
		)
		results = data.get("results", [])
		memories: list[MemoryResponse] = []
		if not isinstance(results, list):
			raise IntegrationError("Hindsight returned an invalid memories list.", 502)

		for result in results:
			if not isinstance(result, dict) or not isinstance(result.get("text"), str):
				continue
			metadata = result.get("metadata")
			if not isinstance(metadata, dict):
				metadata = None
			scores = result.get("scores")
			relevance_score = scores.get("final") if isinstance(scores, dict) else None
			memories.append(
				MemoryResponse(
					id=result.get("id"),
					content=result["text"],
					type=result.get("type") if result.get("type") in {"world", "experience", "observation"} else None,
					category=result.get("context") or result.get("type"),
					created_at=result.get("mentioned_at"),
					relevance_score=relevance_score if isinstance(relevance_score, (float, int)) else None,
					metadata={str(key): str(value) for key, value in metadata.items()} if metadata else None,
					successful_solution=metadata.get("successful_solution") if metadata else None,
				)
			)
		return bank_id, memories

	async def retain_verified_resolution(
		self,
		customer_id: str,
		conversation_id: str,
		document_id: str,
		candidate: ResolutionMemoryCandidate,
	) -> tuple[str, str, str]:
		bank_id = await self.ensure_bank(customer_id)
		issue = redact_card_numbers(candidate.issue.strip())
		troubleshooting = redact_card_numbers(candidate.successful_troubleshooting.strip())
		outcome = redact_card_numbers(candidate.verified_outcome.strip())
		summary = (
			f"Verified support resolution. Previous issue: {issue} "
			f"Successful troubleshooting: {troubleshooting} Verified outcome: {outcome}"
		)
		data = await self._request(
			"POST",
			f"/banks/{quote(bank_id, safe='')}/memories",
			{
				"async": False,
				"items": [
					{
						"content": summary,
						"context": "verified customer support resolution",
						"timestamp": _utc_now(),
						"document_id": document_id,
						"tags": ["support-resolution"],
						"metadata": {
							"source": "verified-support-resolution",
							"conversation_id": conversation_id,
							"successful_solution": troubleshooting,
							"outcome": outcome,
						},
					}
				],
			},
		)
		if data.get("success") is False:
			raise IntegrationError("Hindsight did not confirm that the resolution memory was stored.", 502)
		return bank_id, summary, "verified support resolution"


class SupportAgent:
	def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
		self.settings = settings
		self.client = client

	def _provider_order(self) -> list[str]:
		if self.settings.llm_provider == "openai":
			if not self.settings.openai_api_key:
				raise IntegrationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")
			return ["openai"]
		if self.settings.llm_provider == "ollama":
			return ["ollama"]
		providers = ["openai"] if self.settings.openai_api_key else []
		providers.append("ollama")
		return providers

	@staticmethod
	def _system_prompt(memories: list[MemoryResponse]) -> str:
		if memories:
			memory_context = "\n".join(
				f"- [{memory.category or memory.type or 'memory'}] {memory.content}"
				for memory in memories
			)
		else:
			memory_context = "No relevant Hindsight memories were recalled. Do not claim to remember past interactions."

		return (
			"You are Standford's AI customer-support agent. Use the current issue and only the supplied Hindsight memories. "
			"Be concise, empathetic, and practical. Never claim a past issue or outcome unless present in the context. "
			"Never request or repeat full card numbers, passwords, or authentication secrets. "
			"Return only a JSON object with keys: response (string) and memory_candidate (object or null). "
			"Set memory_candidate only when the latest customer message explicitly confirms that a concrete troubleshooting "
			"step from the immediately preceding assistant response solved the issue. Otherwise it must be null. "
			"When eligible, memory_candidate must contain issue, successful_troubleshooting, and verified_outcome strings. "
			"Do not store chit-chat, temporary glitches, unverified hypotheses, or sensitive data.\n\n"
			f"Recalled Hindsight memories:\n{memory_context}"
		)

	@staticmethod
	def _messages(
		system_prompt: str,
		history: list[dict[str, Any]],
		current_message: str,
	) -> list[dict[str, str]]:
		messages = [{"role": "system", "content": system_prompt}]
		for item in history:
			role = "assistant" if item["role"] == "assistant" else "user"
			messages.append({"role": role, "content": item["content"]})
		messages.append({"role": "user", "content": current_message})
		return messages

	async def _call_openai(self, messages: list[dict[str, str]]) -> str:
		if not self.settings.openai_api_key:
			raise IntegrationError("OPENAI_API_KEY is not configured.")
		try:
			response = await self.client.post(
				f"{self.settings.openai_base_url}/chat/completions",
				headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
				json={
					"model": self.settings.openai_model,
					"messages": messages,
					"temperature": 0.2,
					"response_format": {"type": "json_object"},
				},
			)
		except httpx.RequestError as error:
			raise IntegrationError("OpenAI could not be reached.") from error
		if not response.is_success:
			raise IntegrationError(f"OpenAI returned HTTP {response.status_code}.", 502)
		try:
			return response.json()["choices"][0]["message"]["content"]
		except (ValueError, KeyError, IndexError, TypeError) as error:
			raise IntegrationError("OpenAI returned an invalid chat response.", 502) from error

	async def _call_ollama(self, messages: list[dict[str, str]]) -> str:
		if not self.settings.ollama_base_url or not self.settings.ollama_model:
			raise IntegrationError("Set OLLAMA_BASE_URL and OLLAMA_MODEL to enable the local fallback.")
		try:
			response = await self.client.post(
				f"{self.settings.ollama_base_url}/api/chat",
				json={
					"model": self.settings.ollama_model,
					"messages": messages,
					"stream": False,
					"format": "json",
					"options": {"temperature": 0.2},
				},
			)
		except httpx.RequestError as error:
			raise IntegrationError(
				f"Ollama could not be reached at {self.settings.ollama_base_url}. Start Ollama or configure another provider."
			) from error
		if not response.is_success:
			raise IntegrationError(
				f"Ollama returned HTTP {response.status_code}. Check that model '{self.settings.ollama_model}' is installed.",
				502,
			)
		try:
			return response.json()["message"]["content"]
		except (ValueError, KeyError, TypeError) as error:
			raise IntegrationError("Ollama returned an invalid chat response.", 502) from error

	async def respond(
		self,
		current_message: str,
		history: list[dict[str, Any]],
		memories: list[MemoryResponse],
	) -> tuple[AgentOutput, str]:
		providers = self._provider_order()
		prompt = self._messages(self._system_prompt(memories), history, current_message)
		failures: list[str] = []

		for provider in providers:
			try:
				raw_output = await (self._call_openai(prompt) if provider == "openai" else self._call_ollama(prompt))
				parsed = AgentOutput.model_validate_json(raw_output)
				parsed.response = redact_card_numbers(parsed.response)
				if parsed.memory_candidate:
					parsed.memory_candidate.issue = redact_card_numbers(parsed.memory_candidate.issue)
					parsed.memory_candidate.successful_troubleshooting = redact_card_numbers(
						parsed.memory_candidate.successful_troubleshooting
					)
					parsed.memory_candidate.verified_outcome = redact_card_numbers(
						parsed.memory_candidate.verified_outcome
					)
				return parsed, provider
			except IntegrationError as error:
				failures.append(str(error))
			except (ValidationError, ValueError) as error:
				failures.append(f"{provider} did not return the required structured response.")

		if not providers:
			raise IntegrationError(
				"No LLM provider is configured. Set OPENAI_API_KEY or configure a running Ollama model."
			)
		summary = " ".join(dict.fromkeys(failures))
		raise IntegrationError(
			f"No configured LLM provider is available. Configure OpenAI or start Ollama. {summary}".strip(),
			503,
		)
