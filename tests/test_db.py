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
        assert "protected_files" in tables
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


class TestProtectedFiles:
    def test_add_and_get(self, tmp_db):
        db.init_db()
        db.add_protected_file("*.env")
        db.add_protected_file("package-lock.json")
        patterns = db.get_protected_files()
        pattern_names = [p["pattern"] for p in patterns]
        assert "*.env" in pattern_names
        assert "package-lock.json" in pattern_names

    def test_remove(self, tmp_db):
        db.init_db()
        db.add_protected_file("*.env")
        db.remove_protected_file("*.env")
        patterns = db.get_protected_files()
        assert len(patterns) == 0

    def test_add_duplicate_ignored(self, tmp_db):
        db.init_db()
        db.add_protected_file("*.env")
        db.add_protected_file("*.env")
        patterns = db.get_protected_files()
        assert len(patterns) == 1

    def test_has_timestamps(self, tmp_db):
        db.init_db()
        db.add_protected_file("*.env")
        patterns = db.get_protected_files()
        assert "added" in patterns[0]


class TestPaginatedEvents:
    def test_offset_and_limit(self, tmp_db):
        db.init_db()
        for i in range(20):
            db.log_event(None, None, "Bash", {"command": f"cmd{i}"}, "allow")
        events = db.get_events_paginated(limit=5, offset=5)
        assert len(events) == 5

    def test_search(self, tmp_db):
        db.init_db()
        db.log_event(None, None, "Bash", {"command": "ls -la"}, "allow")
        db.log_event(None, None, "Bash", {"command": "cat foo"}, "allow")
        events = db.get_events_paginated(search="ls")
        assert len(events) == 1

    def test_session_filter(self, tmp_db):
        db.init_db()
        db.log_event("s1", None, "Bash", {"command": "ls"}, "allow")
        db.log_event("s2", None, "Bash", {"command": "pwd"}, "allow")
        events = db.get_events_paginated(session_id="s1")
        assert len(events) == 1
        assert events[0]["session_id"] == "s1"


class TestEventCount:
    def test_total(self, tmp_db):
        db.init_db()
        for i in range(5):
            db.log_event(None, None, "Bash", {"command": f"cmd{i}"}, "allow")
        assert db.get_event_count() == 5

    def test_filtered(self, tmp_db):
        db.init_db()
        db.log_event(None, None, "Bash", {"command": "ls"}, "allow")
        db.log_event(None, None, "WebFetch", {"url": "https://x.com"}, "deny", "blocked")
        assert db.get_event_count(decision="deny") == 1


class TestEventById:
    def test_found(self, tmp_db):
        db.init_db()
        db.log_event(None, None, "Bash", {"command": "ls"}, "allow")
        events = db.get_events(limit=1)
        event = db.get_event_by_id(events[0]["id"])
        assert event is not None
        assert event["tool"] == "Bash"

    def test_not_found(self, tmp_db):
        db.init_db()
        assert db.get_event_by_id(99999) is None


class TestClearAndExport:
    def test_clear(self, tmp_db):
        db.init_db()
        for i in range(3):
            db.log_event(None, None, "Bash", {"command": f"cmd{i}"}, "allow")
        deleted = db.clear_events()
        assert deleted == 3
        assert db.get_event_count() == 0

    def test_export(self, tmp_db):
        db.init_db()
        for i in range(3):
            db.log_event(None, None, "Bash", {"command": f"cmd{i}"}, "allow")
        events = db.export_events()
        assert len(events) == 3


class TestBlocklistDetailed:
    def test_returns_timestamps(self, tmp_db):
        db.init_db()
        db.add_to_blocklist("example.com")
        detailed = db.get_blocklist_detailed()
        assert len(detailed) == 1
        assert detailed[0]["pattern"] == "example.com"
        assert "added" in detailed[0]


class TestGroupedEvents:
    def test_group_by_tool(self, tmp_db):
        db.init_db()
        db.log_event(None, None, "Bash", {"command": "ls"}, "allow")
        db.log_event(None, None, "Bash", {"command": "pwd"}, "allow")
        db.log_event(None, None, "Read", {"file_path": "/x"}, "allow")
        groups = db.get_events_grouped("tool")
        assert len(groups) == 2
        bash_group = next(g for g in groups if g["key"] == "Bash")
        assert bash_group["count"] == 2

    def test_group_by_session(self, tmp_db):
        db.init_db()
        db.log_event("s1", "proj1", "Bash", {"command": "ls"}, "allow")
        db.log_event("s1", "proj1", "Bash", {"command": "pwd"}, "allow")
        db.log_event("s2", "proj2", "Read", {"file_path": "/x"}, "allow")
        groups = db.get_events_grouped("session")
        assert len(groups) == 2
