from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


TICKET_STATUSES = ("open", "in_progress", "resolved", "escalated")


def utc_now() -> str:
	return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Database:
	def __init__(self, database_url: str) -> None:
		if not database_url.startswith("sqlite:///"):
			raise ValueError("DATABASE_URL must use SQLite (sqlite:///path/to/file.db)")
		raw_path = database_url[len("sqlite:///") :]
		if not raw_path:
			raise ValueError("DATABASE_URL must include a SQLite database path")
		self.path = Path(raw_path)

	@contextmanager
	def _connection(self) -> Iterator[sqlite3.Connection]:
		connection = sqlite3.connect(self.path, timeout=10.0)
		connection.row_factory = sqlite3.Row
		connection.execute("PRAGMA foreign_keys = ON")
		connection.execute("PRAGMA busy_timeout = 10000")
		try:
			yield connection
			connection.commit()
		except Exception:
			connection.rollback()
			raise
		finally:
			connection.close()

	def initialize(self) -> None:
		self.path.parent.mkdir(parents=True, exist_ok=True)
		with self._connection() as connection:
			connection.executescript(
				"""
				CREATE TABLE IF NOT EXISTS customers (
					customer_id TEXT PRIMARY KEY,
					name TEXT,
					email TEXT,
					password_hash TEXT,
					created_at TEXT NOT NULL,
					updated_at TEXT NOT NULL
				);

				CREATE TABLE IF NOT EXISTS auth_sessions (
					token_hash TEXT PRIMARY KEY,
					customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
					created_at TEXT NOT NULL,
					expires_at TEXT NOT NULL,
					revoked_at TEXT
				);

				CREATE INDEX IF NOT EXISTS idx_auth_sessions_customer_expiry
					ON auth_sessions(customer_id, expires_at);

				CREATE TABLE IF NOT EXISTS conversations (
					conversation_id TEXT PRIMARY KEY,
					customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
					status TEXT NOT NULL DEFAULT 'in_progress'
						CHECK (status IN ('open', 'in_progress', 'resolved', 'escalated')),
					created_at TEXT NOT NULL,
					updated_at TEXT NOT NULL
				);

				CREATE INDEX IF NOT EXISTS idx_conversations_customer_updated
					ON conversations(customer_id, updated_at DESC);

				CREATE TABLE IF NOT EXISTS messages (
					message_id TEXT PRIMARY KEY,
					conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
					role TEXT NOT NULL CHECK (role IN ('customer', 'assistant')),
					content TEXT NOT NULL,
					created_at TEXT NOT NULL
				);

				CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
					ON messages(conversation_id, created_at);

				CREATE TABLE IF NOT EXISTS tickets (
					ticket_id TEXT PRIMARY KEY,
					customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
					conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE SET NULL,
					subject TEXT NOT NULL,
					status TEXT NOT NULL DEFAULT 'open'
						CHECK (status IN ('open', 'in_progress', 'resolved', 'escalated')),
					created_at TEXT NOT NULL,
					updated_at TEXT NOT NULL
				);

				CREATE INDEX IF NOT EXISTS idx_tickets_customer_created
					ON tickets(customer_id, created_at DESC);

				CREATE TABLE IF NOT EXISTS memory_references (
					reference_id TEXT PRIMARY KEY,
					customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
					conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE SET NULL,
					hindsight_bank_id TEXT NOT NULL,
					hindsight_document_id TEXT NOT NULL,
					category TEXT NOT NULL,
					summary TEXT NOT NULL,
					metadata_json TEXT NOT NULL DEFAULT '{}',
					created_at TEXT NOT NULL,
					UNIQUE(hindsight_bank_id, hindsight_document_id)
				);

				CREATE INDEX IF NOT EXISTS idx_memory_references_customer_created
					ON memory_references(customer_id, created_at DESC);
				"""
			)
			customer_columns = {row["name"] for row in connection.execute("PRAGMA table_info(customers)")}
			if "password_hash" not in customer_columns:
				connection.execute("ALTER TABLE customers ADD COLUMN password_hash TEXT")
			connection.execute(
				"CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_email_unique ON customers(email COLLATE NOCASE) WHERE email IS NOT NULL"
			)

	def ensure_customer(self, customer_id: str, name: str | None = None, email: str | None = None) -> dict[str, Any]:
		now = utc_now()
		with self._connection() as connection:
			connection.execute(
				"""
				INSERT INTO customers(customer_id, name, email, created_at, updated_at)
				VALUES (?, ?, ?, ?, ?)
				ON CONFLICT(customer_id) DO UPDATE SET
					name = COALESCE(excluded.name, customers.name),
					email = COALESCE(excluded.email, customers.email),
					updated_at = excluded.updated_at
				""",
				(customer_id, name, email, now, now),
			)
			row = connection.execute(
				"SELECT customer_id, name, email, created_at, updated_at FROM customers WHERE customer_id = ?",
				(customer_id,),
			).fetchone()
			return dict(row)

	def create_registered_customer(self, name: str, email: str, password_hash: str) -> dict[str, Any]:
		customer_id = f"CUST-{uuid4().hex[:16].upper()}"
		now = utc_now()
		with self._connection() as connection:
			connection.execute(
				"INSERT INTO customers(customer_id, name, email, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
				(customer_id, name, email, password_hash, now, now),
			)
			row = connection.execute(
				"SELECT customer_id, name, email, created_at, updated_at FROM customers WHERE customer_id = ?",
				(customer_id,),
			).fetchone()
		return dict(row)

	def get_registered_customer_by_email(self, email: str) -> dict[str, Any] | None:
		with self._connection() as connection:
			row = connection.execute(
				"SELECT customer_id, name, email, password_hash, created_at, updated_at FROM customers WHERE email = ? COLLATE NOCASE AND password_hash IS NOT NULL",
				(email,),
			).fetchone()
		return dict(row) if row else None

	def get_customer_profile(self, customer_id: str) -> dict[str, Any] | None:
		with self._connection() as connection:
			row = connection.execute(
				"SELECT customer_id, name, email, created_at, updated_at FROM customers WHERE customer_id = ? AND password_hash IS NOT NULL",
				(customer_id,),
			).fetchone()
		return dict(row) if row else None

	def update_customer_profile(self, customer_id: str, name: str, email: str) -> dict[str, Any] | None:
		now = utc_now()
		with self._connection() as connection:
			cursor = connection.execute(
				"UPDATE customers SET name = ?, email = ?, updated_at = ? WHERE customer_id = ? AND password_hash IS NOT NULL",
				(name, email, now, customer_id),
			)
			if cursor.rowcount == 0:
				return None
			row = connection.execute(
				"SELECT customer_id, name, email, created_at, updated_at FROM customers WHERE customer_id = ?",
				(customer_id,),
			).fetchone()
		return dict(row) if row else None

	def create_auth_session(self, token_hash: str, customer_id: str, expires_at: str) -> None:
		with self._connection() as connection:
			connection.execute(
				"INSERT INTO auth_sessions(token_hash, customer_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
				(token_hash, customer_id, utc_now(), expires_at),
			)

	def get_customer_for_session(self, token_hash: str) -> dict[str, Any] | None:
		with self._connection() as connection:
			row = connection.execute(
				"""
				SELECT c.customer_id, c.name, c.email
				FROM auth_sessions AS s
				JOIN customers AS c ON c.customer_id = s.customer_id
				WHERE s.token_hash = ? AND s.revoked_at IS NULL AND s.expires_at > ?
				""",
				(token_hash, utc_now()),
			).fetchone()
		return dict(row) if row else None

	def revoke_auth_session(self, token_hash: str) -> bool:
		with self._connection() as connection:
			cursor = connection.execute(
				"UPDATE auth_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
				(utc_now(), token_hash),
			)
		return cursor.rowcount > 0

	def get_or_create_conversation(self, customer_id: str) -> dict[str, Any]:
		now = utc_now()
		with self._connection() as connection:
			row = connection.execute(
				"""
				SELECT conversation_id, customer_id, status, created_at, updated_at
				FROM conversations
				WHERE customer_id = ? AND status = 'in_progress'
				ORDER BY updated_at DESC
				LIMIT 1
				""",
				(customer_id,),
			).fetchone()
			if row is None:
				conversation_id = str(uuid4())
				connection.execute(
					"INSERT INTO conversations(conversation_id, customer_id, status, created_at, updated_at) VALUES (?, ?, 'in_progress', ?, ?)",
					(conversation_id, customer_id, now, now),
				)
				row = connection.execute(
					"SELECT conversation_id, customer_id, status, created_at, updated_at FROM conversations WHERE conversation_id = ?",
					(conversation_id,),
				).fetchone()
			else:
				connection.execute(
					"UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
					(now, row["conversation_id"]),
				)
				row = connection.execute(
					"SELECT conversation_id, customer_id, status, created_at, updated_at FROM conversations WHERE conversation_id = ?",
					(row["conversation_id"],),
				).fetchone()
			return dict(row)

	def recent_messages(self, conversation_id: str, limit: int = 16) -> list[dict[str, Any]]:
		with self._connection() as connection:
			rows = connection.execute(
				"SELECT message_id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
				(conversation_id, limit),
			).fetchall()
		return [dict(row) for row in reversed(rows)]

	def record_exchange(
		self,
		conversation_id: str,
		customer_message: str,
		assistant_message: str,
	) -> dict[str, str]:
		user_message_id = str(uuid4())
		assistant_message_id = str(uuid4())
		user_created_at = utc_now()
		assistant_created_at = utc_now()
		with self._connection() as connection:
			connection.executemany(
				"INSERT INTO messages(message_id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
				[
					(user_message_id, conversation_id, "customer", customer_message, user_created_at),
					(assistant_message_id, conversation_id, "assistant", assistant_message, assistant_created_at),
				],
			)
			connection.execute(
				"UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
				(assistant_created_at, conversation_id),
			)
		return {
			"customer_message_id": user_message_id,
			"assistant_message_id": assistant_message_id,
			"created_at": assistant_created_at,
		}

	def create_ticket(self, customer_id: str, subject: str) -> dict[str, Any]:
		ticket_id = f"TCK-{uuid4().hex[:12].upper()}"
		now = utc_now()
		with self._connection() as connection:
			conversation = connection.execute(
				"SELECT conversation_id FROM conversations WHERE customer_id = ? AND status = 'in_progress' ORDER BY updated_at DESC LIMIT 1",
				(customer_id,),
			).fetchone()
			conversation_id = conversation["conversation_id"] if conversation else None
			connection.execute(
				"INSERT INTO tickets(ticket_id, customer_id, conversation_id, subject, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'open', ?, ?)",
				(ticket_id, customer_id, conversation_id, subject, now, now),
			)
			row = connection.execute(
				"SELECT ticket_id, customer_id, conversation_id, subject, status, created_at, updated_at FROM tickets WHERE ticket_id = ?",
				(ticket_id,),
			).fetchone()
		return dict(row)

	def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
		with self._connection() as connection:
			row = connection.execute(
				"SELECT ticket_id, customer_id, conversation_id, subject, status, created_at, updated_at FROM tickets WHERE ticket_id = ?",
				(ticket_id,),
			).fetchone()
		return dict(row) if row else None

	def update_ticket_status(self, ticket_id: str, status: str) -> dict[str, Any] | None:
		now = utc_now()
		with self._connection() as connection:
			ticket = connection.execute(
				"SELECT conversation_id FROM tickets WHERE ticket_id = ?",
				(ticket_id,),
			).fetchone()
			if ticket is None:
				return None
			cursor = connection.execute(
				"UPDATE tickets SET status = ?, updated_at = ? WHERE ticket_id = ?",
				(status, now, ticket_id),
			)
			if cursor.rowcount == 0:
				return None
			if ticket["conversation_id"]:
				connection.execute(
					"UPDATE conversations SET status = ?, updated_at = ? WHERE conversation_id = ?",
					(status, now, ticket["conversation_id"]),
				)
			row = connection.execute(
				"SELECT ticket_id, customer_id, conversation_id, subject, status, created_at, updated_at FROM tickets WHERE ticket_id = ?",
				(ticket_id,),
			).fetchone()
		return dict(row) if row else None

	def add_memory_reference(
		self,
		customer_id: str,
		conversation_id: str,
		hindsight_bank_id: str,
		hindsight_document_id: str,
		category: str,
		summary: str,
		metadata: dict[str, str],
	) -> None:
		with self._connection() as connection:
			connection.execute(
				"""
				INSERT OR IGNORE INTO memory_references(
					reference_id, customer_id, conversation_id, hindsight_bank_id,
					hindsight_document_id, category, summary, metadata_json, created_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					str(uuid4()),
					customer_id,
					conversation_id,
					hindsight_bank_id,
					hindsight_document_id,
					category,
					summary,
					json.dumps(metadata, separators=(",", ":")),
					utc_now(),
				),
			)

	def list_memory_references(self, customer_id: str, limit: int = 100) -> list[dict[str, Any]]:
		with self._connection() as connection:
			rows = connection.execute(
				"""
				SELECT reference_id, customer_id, conversation_id, hindsight_bank_id,
					   hindsight_document_id, category, summary, metadata_json, created_at
				FROM memory_references WHERE customer_id = ? ORDER BY created_at DESC LIMIT ?
				""",
				(customer_id, limit),
			).fetchall()
		items = []
		for row in rows:
			item = dict(row)
			item["metadata"] = json.loads(item.pop("metadata_json"))
			items.append(item)
		return items
