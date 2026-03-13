"""Tests for krabb.db."""

import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from krabb import db


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    """Redirect the database to a temporary directory for each test."""
    db_path = tmp_path / "krabb.db"
    with mock.patch.object(db, "DB_DIR", tmp_path), mock.patch.object(
        db, "DB_PATH", db_path
    ):
        yield db_path


class TestInitDb:
    def test_creates_tables(self, tmp_db):
        db.init_db()
        conn = sqlite3.connect(str(tmp_db))
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        conn.close()
        assert "events" in tables
        assert "allowlist" in tables
        assert "config" in tables

    def test_seeds_default_config(self, tmp_db):
        db.init_db()
        assert db.get_config("default_decision") == "allow"
        assert db.get_config("hook_port") == "4243"
        assert db.get_config("dashboard_port") == "4242"
        assert db.get_config("log_bash") == "true"
        assert db.get_config("log_reads") == "true"

    def test_idempotent(self, tmp_db):
        db.init_db()
        db.init_db()  # should not raise
        assert db.get_config("default_decision") == "allow"


class TestLogEvent:
    def test_writes_row(self, tmp_db):
        db.init_db()
        db.log_event("s1", "proj", "WebFetch", {"url": "https://example.com"}, "allow")
        events = db.get_events(limit=10)
        assert len(events) == 1
        assert events[0]["tool"] == "WebFetch"
        assert events[0]["decision"] == "allow"
        assert events[0]["session_id"] == "s1"

    def test_with_reason(self, tmp_db):
        db.init_db()
        db.log_event("s1", None, "WebFetch", {"url": "https://evil.com"}, "deny", "blocked")
        events = db.get_events()
        assert events[0]["reason"] == "blocked"


class TestGetEvents:
    def test_returns_limited(self, tmp_db):
        db.init_db()
        for i in range(10):
            db.log_event(None, None, "Bash", {"command": f"cmd{i}"}, "allow")
        events = db.get_events(limit=5)
        assert len(events) == 5

    def test_filter_by_tool(self, tmp_db):
        db.init_db()
        db.log_event(None, None, "Bash", {"command": "ls"}, "allow")
        db.log_event(None, None, "WebFetch", {"url": "https://x.com"}, "allow")
        events = db.get_events(tool="WebFetch")
        assert len(events) == 1
        assert events[0]["tool"] == "WebFetch"

    def test_filter_by_decision(self, tmp_db):
        db.init_db()
        db.log_event(None, None, "WebFetch", {"url": "a"}, "allow")
        db.log_event(None, None, "WebFetch", {"url": "b"}, "deny", "blocked")
        events = db.get_events(decision="deny")
        assert len(events) == 1
        assert events[0]["decision"] == "deny"

    def test_order_desc(self, tmp_db):
        db.init_db()
        db.log_event(None, None, "Bash", {"command": "first"}, "allow")
        db.log_event(None, None, "Bash", {"command": "second"}, "allow")
        events = db.get_events()
        assert events[0]["id"] > events[1]["id"]


class TestBlocklist:
    def test_add_and_get(self, tmp_db):
        db.init_db()
        db.add_to_blocklist("example.com")
        db.add_to_blocklist("*.github.com")
        patterns = db.get_blocklist()
        assert "example.com" in patterns
        assert "*.github.com" in patterns

    def test_remove(self, tmp_db):
        db.init_db()
        db.add_to_blocklist("example.com")
        db.remove_from_blocklist("example.com")
        assert "example.com" not in db.get_blocklist()

    def test_add_duplicate_ignored(self, tmp_db):
        db.init_db()
        db.add_to_blocklist("example.com")
        db.add_to_blocklist("example.com")
        assert db.get_blocklist().count("example.com") == 1


class TestConfig:
    def test_get_set(self, tmp_db):
        db.init_db()
        db.set_config("custom_key", "custom_value")
        assert db.get_config("custom_key") == "custom_value"

    def test_get_missing(self, tmp_db):
        db.init_db()
        assert db.get_config("nonexistent") is None

    def test_overwrite(self, tmp_db):
        db.init_db()
        db.set_config("default_decision", "deny")
        assert db.get_config("default_decision") == "deny"
