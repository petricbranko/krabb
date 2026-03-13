"""PreToolUse hook HTTP server for krabb.

Listens on localhost:4243 for POST requests from Claude Code hooks.
Also serves GET /events and GET /blocklist for the dashboard.
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from krabb import db
from krabb.blocklist import check_domain


class HookHandler(BaseHTTPRequestHandler):
    """Handles both hook POST requests and dashboard GET requests."""

    def log_message(self, format, *args):  # noqa: A002
        """Suppress default stderr logging."""
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        if path == "/events":
            limit = int(qs.get("limit", ["100"])[0])
            tool = qs.get("tool", [None])[0]
            decision = qs.get("decision", [None])[0]
            events = db.get_events(limit=limit, tool=tool, decision=decision)
            self._send_json({"events": events})

        elif path == "/blocklist":
            patterns = db.get_blocklist()
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
            events_today = db.get_events(limit=10000)
            from datetime import datetime, timezone

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_events = [e for e in events_today if e["ts"].startswith(today)]
            blocked = [e for e in today_events if e["decision"] == "deny"]

            # Most fetched domain
            domains: dict[str, int] = {}
            for e in today_events:
                if e["tool"] in ("WebFetch", "WebSearch"):
                    try:
                        inp = json.loads(e["input"]) if isinstance(e["input"], str) else e["input"]
                        url = inp.get("url") or inp.get("query", "")
                        if url and "://" in url:
                            from krabb.blocklist import extract_domain

                            d = extract_domain(url)
                            if d:
                                domains[d] = domains.get(d, 0) + 1
                    except (json.JSONDecodeError, AttributeError):
                        pass

            top_domain = max(domains, key=domains.get) if domains else None
            self._send_json(
                {
                    "total_today": len(today_events),
                    "blocked_today": len(blocked),
                    "top_domain": top_domain,
                }
            )

        elif path == "/health":
            self._send_json({"status": "ok"})

        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
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

        # Hook handler — process tool use events
        session_id = payload.get("session_id")
        tool_name = payload.get("tool_name", "")
        tool_input = payload.get("tool_input", {})

        decision = "allow"
        reason = None

        default_decision = db.get_config("default_decision") or "allow"
        log_bash = db.get_config("log_bash") == "true"
        log_reads = db.get_config("log_reads") == "true"

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

        elif tool_name in ("Read", "Write"):
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

    def do_DELETE(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/blocklist":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self._send_json({"error": "invalid JSON"}, 400)
                return
            pattern = payload.get("pattern", "")
            if pattern:
                db.remove_from_blocklist(pattern)
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "pattern required"}, 400)
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
