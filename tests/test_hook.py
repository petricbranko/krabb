"""Tests for krabb.hook — the PreToolUse HTTP hook server."""

import json
import threading
from http.server import HTTPServer
from unittest import mock
from urllib.request import Request, urlopen

import pytest

from krabb import db
from krabb.hook import HookHandler


@pytest.fixture()
def hook_server(tmp_path):
    """Start a hook server on a random port with a temp database."""
    db_path = tmp_path / "krabb.db"
    with mock.patch.object(db, "DB_DIR", tmp_path), mock.patch.object(
        db, "DB_PATH", db_path
    ):
        db.init_db()
        server = HTTPServer(("127.0.0.1", 0), HookHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{port}"
        server.shutdown()


def _post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req) as resp:
        return json.loads(resp.read())


def _get(url: str) -> dict:
    with urlopen(url) as resp:
        return json.loads(resp.read())


class TestHookPost:
    def test_allow_webfetch_empty_blocklist(self, hook_server):
        """With an empty blocklist, WebFetch should be allowed."""
        result = _post(
            hook_server,
            {
                "session_id": "test",
                "tool_name": "WebFetch",
                "tool_input": {"url": "https://example.com", "prompt": "test"},
            },
        )
        decision = result["hookSpecificOutput"]["permissionDecision"]
        assert decision == "allow"

    def test_deny_webfetch_in_blocklist(self, hook_server, tmp_path):
        """A domain in the blocklist should be denied."""
        with mock.patch.object(db, "DB_DIR", tmp_path), mock.patch.object(
            db, "DB_PATH", tmp_path / "krabb.db"
        ):
            db.add_to_blocklist("evil.com")

            result = _post(
                hook_server,
                {
                    "session_id": "test",
                    "tool_name": "WebFetch",
                    "tool_input": {"url": "https://evil.com/steal"},
                },
            )
            decision = result["hookSpecificOutput"]["permissionDecision"]
            assert decision == "deny"
            assert result["hookSpecificOutput"].get("permissionDecisionReason")

    def test_allow_webfetch_not_in_blocklist(self, hook_server, tmp_path):
        """A domain not in the blocklist should be allowed."""
        with mock.patch.object(db, "DB_DIR", tmp_path), mock.patch.object(
            db, "DB_PATH", tmp_path / "krabb.db"
        ):
            db.add_to_blocklist("blocked.com")

            result = _post(
                hook_server,
                {
                    "session_id": "test",
                    "tool_name": "WebFetch",
                    "tool_input": {"url": "https://trusted.com/page"},
                },
            )
            decision = result["hookSpecificOutput"]["permissionDecision"]
            assert decision == "allow"

    def test_bash_logged_and_allowed(self, hook_server, tmp_path):
        """Bash commands should be logged and always allowed."""
        with mock.patch.object(db, "DB_DIR", tmp_path), mock.patch.object(
            db, "DB_PATH", tmp_path / "krabb.db"
        ):
            result = _post(
                hook_server,
                {
                    "session_id": "test",
                    "tool_name": "Bash",
                    "tool_input": {"command": "ls -la"},
                },
            )
            decision = result["hookSpecificOutput"]["permissionDecision"]
            assert decision == "allow"

            events = db.get_events(tool="Bash")
            assert len(events) >= 1

    def test_read_logged_and_allowed(self, hook_server, tmp_path):
        """Read tool calls should be logged and allowed."""
        with mock.patch.object(db, "DB_DIR", tmp_path), mock.patch.object(
            db, "DB_PATH", tmp_path / "krabb.db"
        ):
            result = _post(
                hook_server,
                {
                    "session_id": "test",
                    "tool_name": "Read",
                    "tool_input": {"file_path": "/etc/hosts"},
                },
            )
            decision = result["hookSpecificOutput"]["permissionDecision"]
            assert decision == "allow"


class TestHookGetEndpoints:
    def test_get_events(self, hook_server):
        data = _get(hook_server + "/events")
        assert "events" in data

    def test_get_blocklist(self, hook_server):
        data = _get(hook_server + "/blocklist")
        assert "patterns" in data

    def test_get_health(self, hook_server):
        data = _get(hook_server + "/health")
        assert data["status"] == "ok"

    def test_get_stats(self, hook_server):
        data = _get(hook_server + "/stats")
        assert "total_today" in data
