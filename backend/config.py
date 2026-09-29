from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _positive_float(name: str, default: float) -> float:
	raw_value = os.getenv(name)
	if raw_value is None:
		return default
	try:
		value = float(raw_value)
	except ValueError as error:
		raise ValueError(f"{name} must be a positive number") from error
	if value <= 0:
		raise ValueError(f"{name} must be a positive number")
	return value


def _positive_int(name: str, default: int) -> int:
	raw_value = os.getenv(name)
	if raw_value is None:
		return default
	try:
		value = int(raw_value)
	except ValueError as error:
		raise ValueError(f"{name} must be a positive integer") from error
	if value <= 0:
		raise ValueError(f"{name} must be a positive integer")
	return value


@dataclass(frozen=True, slots=True)
class Settings:
	database_url: str
	cors_origins: tuple[str, ...]
	llm_provider: str
	openai_api_key: str | None
	openai_base_url: str
	openai_model: str
	ollama_base_url: str
	ollama_model: str
	hindsight_api_url: str | None
	hindsight_api_key: str | None
	hindsight_bank_prefix: str
	request_timeout_seconds: float
	auth_token_ttl_seconds: int

	@classmethod
	def from_environment(cls) -> Settings:
		origins_value = os.getenv(
			"CORS_ORIGINS",
			"http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
		)
		origins = tuple(origin.strip().rstrip("/") for origin in origins_value.split(",") if origin.strip())
		provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()
		if provider not in {"auto", "openai", "ollama"}:
			raise ValueError("LLM_PROVIDER must be one of: auto, openai, ollama")

		hindsight_url = os.getenv("HINDSIGHT_API_URL", "").strip().rstrip("/") or None
		hindsight_key = os.getenv("HINDSIGHT_API_KEY", "").strip() or None

		return cls(
			database_url=os.getenv("DATABASE_URL", "sqlite:///./db.sqlite3").strip(),
			cors_origins=origins,
			llm_provider=provider,
			openai_api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
			openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
			openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
			ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/"),
			ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip(),
			hindsight_api_url=hindsight_url,
			hindsight_api_key=hindsight_key,
			hindsight_bank_prefix=os.getenv("HINDSIGHT_BANK_PREFIX", "standford-customer").strip(),
			request_timeout_seconds=_positive_float("REQUEST_TIMEOUT_SECONDS", 30.0),
			auth_token_ttl_seconds=_positive_int("AUTH_TOKEN_TTL_SECONDS", 28800),
		)


settings = Settings.from_environment()
