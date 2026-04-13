"""krabb CLI — entry point for all commands."""

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from krabb import __version__, db
from krabb.installer import install, uninstall

KRABB_DIR = Path.home() / ".krabb"
PID_FILE = KRABB_DIR / "hook.pid"
DASHBOARD_PID_FILE = KRABB_DIR / "dashboard.pid"


# -- ANSI helpers (only when stdout is a tty) --

def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m" if _supports_color() else text


def _green(text: str) -> str:
    return f"\033[32m{text}\033[0m" if _supports_color() else text


def _red(text: str) -> str:
    return f"\033[31m{text}\033[0m" if _supports_color() else text


def _yellow(text: str) -> str:
    return f"\033[33m{text}\033[0m" if _supports_color() else text


def _dim(text: str) -> str:
    return f"\033[2m{text}\033[0m" if _supports_color() else text


# -- Daemon helpers --

def _is_hook_running() -> int | None:
    """Return PID if hook is running, else None."""
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        PID_FILE.unlink(missing_ok=True)
        return None


def _start_hook_daemon() -> int:
    """Start the hook server as a background process, return PID."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "krabb.hook"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    KRABB_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(proc.pid))
    return proc.pid


def _stop_hook_daemon() -> bool:
    """Stop a running hook daemon. Returns True if stopped."""
    pid = _is_hook_running()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        return True
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        return False


def _is_dashboard_running() -> int | None:
    """Return PID if dashboard is running, else None."""
    if not DASHBOARD_PID_FILE.exists():
        return None
    try:
        pid = int(DASHBOARD_PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        DASHBOARD_PID_FILE.unlink(missing_ok=True)
        return None


def _start_dashboard_daemon() -> int:
    """Start the dashboard as a background process, return PID."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "krabb.dashboard.server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    KRABB_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PID_FILE.write_text(str(proc.pid))
    return proc.pid


def _stop_dashboard_daemon() -> bool:
    """Stop a running dashboard daemon. Returns True if stopped."""
    pid = _is_dashboard_running()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        DASHBOARD_PID_FILE.unlink(missing_ok=True)
        return True
    except ProcessLookupError:
        DASHBOARD_PID_FILE.unlink(missing_ok=True)
        return False


# -- Commands --

def cmd_init(_args: argparse.Namespace) -> None:
    db.init_db()
    installed = install()

    if installed:
        print(_green("Hook registered in ~/.claude/settings.json"))
    else:
        print(_yellow("Hook already registered in ~/.claude/settings.json"))

    pid = _is_hook_running()
    if pid:
        print(_yellow(f"Hook server already running (PID {pid})"))
    else:
        pid = _start_hook_daemon()
        print(_green(f"Hook server started (PID {pid})"))

    print()
    print(_bold("krabb is ready!"))
    print(f"  Database: {db.DB_PATH}")
    print("  Hook:     http://127.0.0.1:4243")
    print(f"  Dashboard: run {_bold('krabb dashboard')}")
    print()
    print(_dim("All Claude Code tool calls are now being logged."))
    print(_dim("Use 'krabb blocklist add <pattern>' to restrict web access."))


def cmd_status(_args: argparse.Namespace) -> None:
    pid = _is_hook_running()
    if pid:
        print(f"Hook server: {_green('running')} (PID {pid})")
    else:
        print(f"Hook server: {_red('stopped')}")

    print(f"Database:    {db.DB_PATH}")
    if db.DB_PATH.exists():
        total = len(db.get_events(limit=100000))
        print(f"Events:      {total}")
    else:
        print(f"Events:      {_dim('(no database yet — run krabb init)')}")

    patterns = db.get_blocklist() if db.DB_PATH.exists() else []
    print(f"Blocklist:   {len(patterns)} pattern(s)")


def cmd_logs(args: argparse.Namespace) -> None:
    events = db.get_events(
        limit=args.limit,
        tool=args.tool,
        decision=args.decision,
    )

    if not events:
        print(_dim("No events found."))
        return

    for e in reversed(events):
        ts = e["ts"][:19].replace("T", " ")
        tool = e["tool"]
        decision = _green(e["decision"]) if e["decision"] == "allow" else _red(e["decision"])

        # Truncate input for display
        try:
            inp = json.loads(e["input"]) if isinstance(e["input"], str) else e["input"]
            summary = _summarize_input(e["tool"], inp)
        except (json.JSONDecodeError, TypeError):
            summary = str(e["input"])[:60]

        reason = f" ({e['reason']})" if e.get("reason") else ""
        print(f"{_dim(ts)}  {tool:<10} {decision}{reason}  {summary}")


def _summarize_input(tool: str, inp: dict) -> str:
    """Create a short summary of tool input for log display."""
    if tool == "WebFetch":
        return inp.get("url", "")[:80]
    if tool == "WebSearch":
        return inp.get("query", "")[:80]
    if tool == "Bash":
        return inp.get("command", "")[:80]
    if tool in ("Read", "Write"):
        return inp.get("file_path", "")[:80]
    return json.dumps(inp)[:80]


def cmd_dashboard(args: argparse.Namespace) -> None:
    if args.daemon:
        pid = _is_dashboard_running()
        if pid:
            print(_yellow(f"Dashboard already running (PID {pid})"))
        else:
            pid = _start_dashboard_daemon()
            print(_green(f"Dashboard started (PID {pid})"))
            print(f"  http://127.0.0.1:{int(db.get_config('dashboard_port') or '4242')}")
        return

    import webbrowser
    from krabb.dashboard.server import run_dashboard

    port = int(db.get_config("dashboard_port") or "4242")
    webbrowser.open(f"http://127.0.0.1:{port}")
    run_dashboard(port=port)


def cmd_blocklist(args: argparse.Namespace) -> None:
    action = args.action

    if action == "list":
        patterns = db.get_blocklist()
        if not patterns:
            print(_dim("Blocklist is empty — nothing blocked."))
        else:
            print(_bold(f"Blocklist ({len(patterns)} patterns):"))
            for p in patterns:
                print(f"  {p}")

    elif action == "add":
        if not args.pattern:
            print(_red("Error: pattern required"))
            sys.exit(1)
        db.add_to_blocklist(args.pattern)
        print(_green(f"Added: {args.pattern}"))

    elif action == "remove":
        if not args.pattern:
            print(_red("Error: pattern required"))
            sys.exit(1)
        db.remove_from_blocklist(args.pattern)
        print(_green(f"Removed: {args.pattern}"))


def cmd_commands(args: argparse.Namespace) -> None:
    action = args.action

    if action == "list":
        patterns = db.get_blocked_commands()
        if not patterns:
            print(_dim("No blocked commands — nothing blocked."))
        else:
            print(_bold(f"Blocked commands ({len(patterns)} patterns):"))
            for p in patterns:
                print(f"  {p}")

    elif action == "add":
        if not args.pattern:
            print(_red("Error: pattern required"))
            sys.exit(1)
        db.add_blocked_command(args.pattern)
        print(_green(f"Added: {args.pattern}"))

    elif action == "remove":
        if not args.pattern:
            print(_red("Error: pattern required"))
            sys.exit(1)
        db.remove_blocked_command(args.pattern)
        print(_green(f"Removed: {args.pattern}"))


def cmd_proxy(_args: argparse.Namespace) -> None:
    """Read hook JSON from stdin, POST to hook server, print response."""
    import urllib.request

    payload = sys.stdin.read()
    port = 4243
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}",
        data=payload.encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            sys.stdout.write(resp.read().decode())
    except Exception:
        # Fail-open: allow the tool call if hook server is unreachable
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }))


def cmd_hook(args: argparse.Namespace) -> None:
    if args.daemon:
        pid = _is_hook_running()
        if pid:
            print(_yellow(f"Hook server already running (PID {pid})"))
        else:
            pid = _start_hook_daemon()
            print(_green(f"Hook server started (PID {pid})"))
        return

    from krabb.hook import run_server
    run_server()


def cmd_uninstall(_args: argparse.Namespace) -> None:
    _stop_hook_daemon()
    _stop_dashboard_daemon()
    removed = uninstall()
    if removed:
        print(_green("Hook removed from ~/.claude/settings.json"))
    else:
        print(_yellow("Hook not found in settings.json"))
    print(_dim("Database preserved at ~/.krabb/krabb.db"))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="krabb",
        description="Web access analytics and control for Claude Code",
    )
    parser.add_argument(
        "--version", action="version", version=f"krabb {__version__}"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Install hook and start daemon")
    sub.add_parser("status", help="Show daemon status and stats")

    logs_p = sub.add_parser("logs", help="Show recent events")
    logs_p.add_argument("--limit", type=int, default=50)
    logs_p.add_argument("--tool", type=str, default=None)
    logs_p.add_argument("--decision", type=str, default=None)

    dash_p = sub.add_parser("dashboard", help="Open the dashboard in a browser")
    dash_p.add_argument("-d", "--daemon", action="store_true", help="Run in background")

    al_p = sub.add_parser("blocklist", help="Manage domain blocklist")
    al_p.add_argument("action", choices=["list", "add", "remove"])
    al_p.add_argument("pattern", nargs="?", default=None)

    cmd_p = sub.add_parser("commands", help="Manage blocked commands")
    cmd_p.add_argument("action", choices=["list", "add", "remove"])
    cmd_p.add_argument("pattern", nargs="?", default=None)

    hook_p = sub.add_parser("hook", help="Run the hook server")
    hook_p.add_argument("-d", "--daemon", action="store_true", help="Run in background")
    sub.add_parser("proxy", help="Stdin/stdout proxy for Claude Code hooks")
    sub.add_parser("uninstall", help="Remove hook from Claude settings")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Ensure db is initialized for all commands except init/hook
    if args.command not in ("init", "hook") and db.DB_PATH.exists():
        db.init_db()

    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "logs": cmd_logs,
        "dashboard": cmd_dashboard,
        "blocklist": cmd_blocklist,
        "commands": cmd_commands,
        "hook": cmd_hook,
        "proxy": cmd_proxy,
        "uninstall": cmd_uninstall,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
