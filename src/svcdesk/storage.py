# ai-generated: 70% - SQLite storage extracted; reviewed by the student
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(os.getenv("SVCDESK_DB", "svcdesk.db"))
DB_LOCK = threading.RLock()


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(str(DB_PATH), timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connection() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS tickets ("
            "id TEXT PRIMARY KEY, ticket_json TEXT NOT NULL)"
        )
        connection.commit()


def get_ticket(ticket_id: str) -> dict[str, Any] | None:
    with DB_LOCK, _connection() as connection:
        row = connection.execute(
            "SELECT ticket_json FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
    return json.loads(row["ticket_json"]) if row else None


def save_ticket(ticket: dict[str, Any]) -> None:
    with DB_LOCK, _connection() as connection:
        connection.execute(
            "INSERT INTO tickets (id, ticket_json) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET ticket_json = excluded.ticket_json",
            (ticket["id"], json.dumps(ticket, separators=(",", ":"), ensure_ascii=False)),
        )
        connection.commit()


def all_tickets() -> list[dict[str, Any]]:
    with DB_LOCK, _connection() as connection:
        rows = connection.execute(
            "SELECT ticket_json FROM tickets ORDER BY rowid ASC"
        ).fetchall()
    return [json.loads(row["ticket_json"]) for row in rows]
