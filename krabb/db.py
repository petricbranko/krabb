"""SQLite storage for krabb events, blocklist, and config."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_DIR = Path.home() / ".krabb"
DB_PATH = DB_DIR / "krabb.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    session_id  TEXT,
    project     TEXT,
    tool        TEXT NOT NULL,
    input       TEXT NOT NULL,
    decision    TEXT NOT NULL,
    reason      TEXT
);

CREATE TABLE IF NOT EXISTS allowlist (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    added   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
"""

_DEFAULTS = {
    "default_decision": "allow",
    "hook_port": "4243",
    "dashboard_port": "4242",
    "log_bash": "true",
    "log_reads": "true",
}


def _connect() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables and seed default config values."""
    conn = _connect()
    try:
        conn.executescript(_SCHEMA)
        for key, value in _DEFAULTS.items():
            conn.execute(
                "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                (key, value),
            )
        conn.commit()
    finally:
        conn.close()


def log_event(
    session_id: str | None,
    project: str | None,
    tool: str,
    tool_input: dict,
    decision: str,
    reason: str | None = None,
) -> None:
    """Write a tool-use event to the database."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO events (ts, session_id, project, tool, input, decision, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                session_id,
                project,
                tool,
                json.dumps(tool_input),
                decision,
                reason,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_events(
    limit: int = 100,
    tool: str | None = None,
    decision: str | None = None,
) -> list[dict]:
    """Return recent events, optionally filtered by tool or decision."""
    conn = _connect()
    try:
        query = "SELECT * FROM events"
        params: list[str] = []
        clauses: list[str] = []
        if tool:
            clauses.append("tool = ?")
            params.append(tool)
        if decision:
            clauses.append("decision = ?")
            params.append(decision)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(str(limit))
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_to_blocklist(pattern: str) -> None:
    """Add a domain pattern to the blocklist."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO allowlist (pattern, added) VALUES (?, ?)",
            (pattern, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def remove_from_blocklist(pattern: str) -> None:
    """Remove a domain pattern from the blocklist."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM allowlist WHERE pattern = ?", (pattern,))
        conn.commit()
    finally:
        conn.close()


def get_blocklist() -> list[str]:
    """Return all blocklist patterns."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT pattern FROM allowlist ORDER BY id").fetchall()
        return [r["pattern"] for r in rows]
    finally:
        conn.close()


def get_config(key: str) -> str | None:
    """Get a config value by key."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT value FROM config WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def set_config(key: str, value: str) -> None:
    """Set a config value."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()
