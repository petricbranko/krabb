"""PreToolUse hook HTTP server for krabb.

Listens on localhost:4243 for POST requests from Claude Code hooks.
Also serves GET /events and GET /blocklist for the dashboard.
"""

from __future__ import annotations

import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from krabb import db
from krabb.blocklist import check_domain
from krabb.commandblock import check_command_blocked
from krabb.fileprotect import check_file_protected


class HookHandler(BaseHTTPRequestHandler):
    """Handles both hook POST requests and dashboard GET requests."""

    def log_message(self, format, *args):  # noqa: A002
        """Suppress default stderr logging."""
        pass

    def _send_json(self, data: dict | list, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        content_length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_length)

    def _parse_json_body(self) -> dict | None:
        body = self._read_body()
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return None

    def do_OPTIONS(self):  # noqa: N802
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        if path == "/events":
            limit = int(qs.get("limit", ["100"])[0])
            offset = int(qs.get("offset", ["0"])[0])
            tool = qs.get("tool", [None])[0]
            decision = qs.get("decision", [None])[0]
            search = qs.get("search", [None])[0]
            session_id = qs.get("session_id", [None])[0]
            group_by = qs.get("group_by", [None])[0]
            date_from = qs.get("date_from", [None])[0]
            date_to = qs.get("date_to", [None])[0]

            if group_by:
                groups = db.get_events_grouped(group_by=group_by, limit=limit)
                self._send_json({"groups": groups})
            else:
                events = db.get_events_paginated(
                    limit=limit, offset=offset, tool=tool,
                    decision=decision, search=search, session_id=session_id,
                    date_from=date_from, date_to=date_to,
                )
                self._send_json({"events": events})

        elif path == "/events/count":
            tool = qs.get("tool", [None])[0]
            decision = qs.get("decision", [None])[0]
            search = qs.get("search", [None])[0]
            session_id = qs.get("session_id", [None])[0]
            date_from = qs.get("date_from", [None])[0]
            date_to = qs.get("date_to", [None])[0]
            count = db.get_event_count(
                tool=tool, decision=decision,
                search=search, session_id=session_id,
                date_from=date_from, date_to=date_to,
            )
            self._send_json({"count": count})

        elif path == "/events/export":
            events = db.export_events()
            self._send_json(events)

        elif re.match(r"^/events/(\d+)$", path):
            event_id = int(re.match(r"^/events/(\d+)$", path).group(1))
            event = db.get_event_by_id(event_id)
            if event:
                self._send_json({"event": event})
            else:
                self._send_json({"error": "not found"}, 404)

        elif path == "/blocklist":
            patterns = db.get_blocklist_detailed()
            self._send_json({"patterns": patterns})

        elif path == "/protected-files":
            patterns = db.get_protected_files()
            self._send_json({"patterns": patterns})

        elif path == "/blocked-commands":
            patterns = db.get_blocked_commands_detailed()
            self._send_json({"patterns": patterns})

        elif path == "/config":
            keys = [
                "default_decision",
                "hook_port",
                "dashboard_port",
                "log_bash",
                "log_reads",
            ]
            config = {k: db.get_config(k) for k in keys}
            self._send_json({"config": config})

        elif path == "/stats":
            stats = db.get_stats_sql()
            self._send_json(stats)

        elif path == "/health":
            self._send_json({"status": "ok"})

        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        payload = self._parse_json_body()
        if payload is None:
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # Dashboard blocklist management
        if path == "/blocklist":
            pattern = payload.get("pattern", "")
            if pattern:
                db.add_to_blocklist(pattern)
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "pattern required"}, 400)
            return

        # Dashboard protected files management
        if path == "/protected-files":
            pattern = payload.get("pattern", "")
            if pattern:
                db.add_protected_file(pattern)
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "pattern required"}, 400)
            return

        # Dashboard blocked commands management
        if path == "/blocked-commands":
            pattern = payload.get("pattern", "")
            if pattern:
                db.add_blocked_command(pattern)
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "pattern required"}, 400)
            return

        # Hook handler — process tool use events
        session_id = payload.get("session_id")
        tool_name = payload.get("tool_name", "")
        tool_input = payload.get("tool_input", {})

        decision = "allow"
        reason = None

        default_decision = db.get_config("default_decision") or "allow"
        log_bash = db.get_config("log_bash") == "true"
        log_reads = db.get_config("log_reads") == "true"

        # Check blocked commands first (applies to all tools)
        blocked_patterns = db.get_blocked_commands()
        if blocked_patterns:
            command = tool_input.get("command", "")
            matched = check_command_blocked(tool_name, command, blocked_patterns)
            if matched:
                decision = "deny"
                reason = f"Command blocked by krabb: {matched}"
                db.log_event(
                    session_id=session_id,
                    project=payload.get("project"),
                    tool=tool_name,
                    tool_input=tool_input,
                    decision=decision,
                    reason=reason,
                )
                self._send_json(_hook_response(decision, reason))
                return

        if tool_name in ("WebFetch", "WebSearch"):
            url = tool_input.get("url") or tool_input.get("query", "")
            patterns = db.get_blocklist()
            if patterns and check_domain(url, patterns):
                decision = "deny"
                reason = "Fetch blocked by krabb, visit dashboard"
            else:
                decision = default_decision

        elif tool_name == "Bash":
            if not log_bash:
                self._send_json(_hook_response("allow"))
                return
            decision = "allow"

        elif tool_name in ("Write", "Edit"):
            file_path = tool_input.get("file_path", "")
            protected = [p["pattern"] for p in db.get_protected_files()]
            if file_path and protected and check_file_protected(file_path, protected):
                decision = "deny"
                reason = "File protected by krabb"
            elif tool_name == "Write" and not log_reads:
                self._send_json(_hook_response("allow"))
                return
            else:
                decision = "allow"

        elif tool_name == "Read":
            if not log_reads:
                self._send_json(_hook_response("allow"))
                return
            decision = "allow"

        else:
            decision = default_decision

        db.log_event(
            session_id=session_id,
            project=payload.get("project"),
            tool=tool_name,
            tool_input=tool_input,
            decision=decision,
            reason=reason,
        )

        self._send_json(_hook_response(decision, reason))

    def do_PUT(self):  # noqa: N802
        payload = self._parse_json_body()
        if payload is None:
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/config":
            key = payload.get("key", "")
            value = payload.get("value", "")
            valid_keys = {"default_decision", "log_bash", "log_reads", "hook_port", "dashboard_port"}
            if key in valid_keys and value:
                db.set_config(key, value)
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "invalid key or value"}, 400)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_DELETE(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/blocklist":
            payload = self._parse_json_body()
            if payload is None:
                return
            pattern = payload.get("pattern", "")
            if pattern:
                db.remove_from_blocklist(pattern)
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "pattern required"}, 400)

        elif path == "/protected-files":
            payload = self._parse_json_body()
            if payload is None:
                return
            pattern = payload.get("pattern", "")
            if pattern:
                db.remove_protected_file(pattern)
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "pattern required"}, 400)

        elif path == "/blocked-commands":
            payload = self._parse_json_body()
            if payload is None:
                return
            pattern = payload.get("pattern", "")
            if pattern:
                db.remove_blocked_command(pattern)
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "pattern required"}, 400)

        elif path == "/events":
            count = db.clear_events()
            self._send_json({"ok": True, "deleted": count})

        else:
            self._send_json({"error": "not found"}, 404)


def _hook_response(decision: str, reason: str | None = None) -> dict:
    """Build the Claude Code hook response envelope."""
    resp: dict = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
        }
    }
    if reason:
        resp["hookSpecificOutput"]["permissionDecisionReason"] = reason
    return resp


def run_server(port: int | None = None) -> None:
    """Start the hook HTTP server (blocking)."""
    db.init_db()
    if port is None:
        port = int(db.get_config("hook_port") or "4243")
    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("127.0.0.1", port), HookHandler)
    print(f"krabb hook server listening on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nkrabb hook server stopped.")
        server.server_close()


if __name__ == "__main__":
    run_server()
