"""Install/uninstall krabb hooks in Claude Code settings."""

import json
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
KRABB_DIR = Path.home() / ".krabb"

HOOK_ENTRY = {
    "matcher": "WebFetch|WebSearch|Bash|Read|Write",
    "hooks": [
        {
            "type": "command",
            "command": "curl -s -m 5 -X POST -H 'Content-Type: application/json' -d @- http://127.0.0.1:4243",
            "timeout": 5,
        }
    ],
}


def _is_krabb_hook(entry: dict) -> bool:
    """Check if a hook entry belongs to krabb."""
    hooks = entry.get("hooks", [])
    return any(
        "localhost:4243" in h.get("command", "") or
        h.get("url", "").startswith("http://localhost:4243")
        for h in hooks
    )


def install() -> bool:
    """Register the krabb hook in ~/.claude/settings.json.

    Returns True if installed, False if already present.
    """
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    KRABB_DIR.mkdir(parents=True, exist_ok=True)

    settings: dict = {}
    if SETTINGS_PATH.exists():
        settings = json.loads(SETTINGS_PATH.read_text())

    hooks = settings.setdefault("hooks", {})
    pre_tool_use = hooks.setdefault("PreToolUse", [])

    # Check if krabb is already registered
    for entry in pre_tool_use:
        if _is_krabb_hook(entry):
            return False

    pre_tool_use.append(HOOK_ENTRY)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n")
    return True


def uninstall() -> bool:
    """Remove the krabb hook from ~/.claude/settings.json.

    Returns True if removed, False if not found.
    """
    if not SETTINGS_PATH.exists():
        return False

    settings = json.loads(SETTINGS_PATH.read_text())
    hooks = settings.get("hooks", {})
    pre_tool_use = hooks.get("PreToolUse", [])

    original_len = len(pre_tool_use)
    pre_tool_use = [e for e in pre_tool_use if not _is_krabb_hook(e)]

    if len(pre_tool_use) == original_len:
        return False

    hooks["PreToolUse"] = pre_tool_use
    # Clean up empty structures
    if not pre_tool_use:
        del hooks["PreToolUse"]
    if not hooks:
        del settings["hooks"]

    SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n")
    return True
