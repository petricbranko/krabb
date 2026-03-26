"""SQLite storage for krabb events, blocklist, and config."""

from __future__ import annotations

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

CREATE TABLE IF NOT EXISTS protected_files (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    added   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts);
CREATE INDEX IF NOT EXISTS idx_events_tool ON events (tool);
CREATE INDEX IF NOT EXISTS idx_events_decision ON events (decision);
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


def get_blocklist_detailed() -> list[dict]:
    """Return all blocklist patterns with timestamps."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT pattern, added FROM allowlist ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
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


# ---------------------------------------------------------------------------
# Protected files
# ---------------------------------------------------------------------------


def add_protected_file(pattern: str) -> None:
    """Add a file pattern to the protected files list."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO protected_files (pattern, added) VALUES (?, ?)",
            (pattern, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def remove_protected_file(pattern: str) -> None:
    """Remove a file pattern from the protected files list."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM protected_files WHERE pattern = ?", (pattern,))
        conn.commit()
    finally:
        conn.close()


def get_protected_files() -> list[dict]:
    """Return all protected file patterns with timestamps."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT pattern, added FROM protected_files ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Paginated / filtered events
# ---------------------------------------------------------------------------


def _build_event_filter(
    tool: str | None = None,
    decision: str | None = None,
    search: str | None = None,
    session_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[str, list[str]]:
    """Build WHERE clause and params for event queries."""
    clauses: list[str] = []
    params: list[str] = []
    if tool:
        clauses.append("tool = ?")
        params.append(tool)
    if decision:
        clauses.append("decision = ?")
        params.append(decision)
    if search:
        clauses.append("(input LIKE ? OR tool LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    if date_from:
        clauses.append("ts >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("ts < ?")
        params.append(date_to + "T99")  # ensures entire day is included
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def get_events_paginated(
    limit: int = 50,
    offset: int = 0,
    tool: str | None = None,
    decision: str | None = None,
    search: str | None = None,
    session_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Return events with pagination and optional filters."""
    conn = _connect()
    try:
        where, params = _build_event_filter(
            tool, decision, search, session_id, date_from, date_to,
        )
        query = f"SELECT * FROM events{where} ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([str(limit), str(offset)])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_event_count(
    tool: str | None = None,
    decision: str | None = None,
    search: str | None = None,
    session_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> int:
    """Return total count of events matching filters."""
    conn = _connect()
    try:
        where, params = _build_event_filter(
            tool, decision, search, session_id, date_from, date_to,
        )
        row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM events{where}", params
        ).fetchone()
        return row["cnt"]
    finally:
        conn.close()


def get_event_by_id(event_id: int) -> dict | None:
    """Return a single event by ID."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_events_grouped(group_by: str, limit: int = 50) -> list[dict]:
    """Return events grouped by tool, session, or domain."""
    conn = _connect()
    try:
        if group_by == "tool":
            rows = conn.execute(
                "SELECT tool as key, COUNT(*) as count, MAX(ts) as latest_ts "
                "FROM events GROUP BY tool ORDER BY count DESC LIMIT ?",
                (limit,),
            ).fetchall()
        elif group_by == "session":
            rows = conn.execute(
                "SELECT session_id as key, project, COUNT(*) as count, "
                "MAX(ts) as latest_ts "
                "FROM events GROUP BY session_id ORDER BY count DESC LIMIT ?",
                (limit,),
            ).fetchall()
        elif group_by == "domain":
            # Domain grouping requires extracting from JSON input — use
            # a simpler approach: fetch web events and aggregate in Python.
            web_events = conn.execute(
                "SELECT input, ts FROM events "
                "WHERE tool IN ('WebFetch', 'WebSearch') "
                "ORDER BY id DESC LIMIT 10000"
            ).fetchall()
            from krabb.blocklist import extract_domain

            domains: dict[str, dict] = {}
            for e in web_events:
                try:
                    inp = json.loads(e["input"])
                    url = inp.get("url") or inp.get("query", "")
                    if url and "://" in url:
                        d = extract_domain(url)
                        if d:
                            if d not in domains:
                                domains[d] = {"key": d, "count": 0, "latest_ts": e["ts"]}
                            domains[d]["count"] += 1
                except (json.JSONDecodeError, AttributeError):
                    pass
            sorted_domains = sorted(
                domains.values(), key=lambda x: x["count"], reverse=True
            )
            return sorted_domains[:limit]
        else:
            return []
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_stats_sql() -> dict:
    """Compute stats using SQL aggregation."""
    conn = _connect()
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM events WHERE ts >= ?", (today,)
        ).fetchone()["cnt"]

        blocked = conn.execute(
            "SELECT COUNT(*) as cnt FROM events WHERE ts >= ? AND decision = 'deny'",
            (today,),
        ).fetchone()["cnt"]

        sessions = conn.execute(
            "SELECT COUNT(DISTINCT session_id) as cnt FROM events WHERE ts >= ?",
            (today,),
        ).fetchone()["cnt"]

        # Tool breakdown
        tool_rows = conn.execute(
            "SELECT tool, COUNT(*) as cnt FROM events WHERE ts >= ? GROUP BY tool",
            (today,),
        ).fetchall()
        by_tool = {r["tool"]: r["cnt"] for r in tool_rows}

        # Top domain — need to parse JSON in Python
        web_events = conn.execute(
            "SELECT input FROM events WHERE ts >= ? AND tool IN ('WebFetch', 'WebSearch')",
            (today,),
        ).fetchall()
        from krabb.blocklist import extract_domain

        domains: dict[str, int] = {}
        for e in web_events:
            try:
                inp = json.loads(e["input"])
                url = inp.get("url") or inp.get("query", "")
                if url and "://" in url:
                    d = extract_domain(url)
                    if d:
                        domains[d] = domains.get(d, 0) + 1
            except (json.JSONDecodeError, AttributeError):
                pass
        top_domain = max(domains, key=domains.get) if domains else None

        return {
            "total_today": total,
            "blocked_today": blocked,
            "top_domain": top_domain,
            "active_sessions": sessions,
            "by_tool": by_tool,
        }
    finally:
        conn.close()


def clear_events() -> int:
    """Delete all events. Returns count deleted."""
    conn = _connect()
    try:
        count = conn.execute("SELECT COUNT(*) as cnt FROM events").fetchone()["cnt"]
        conn.execute("DELETE FROM events")
        conn.commit()
        return count
    finally:
        conn.close()


def export_events() -> list[dict]:
    """Return all events for export."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM events ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
