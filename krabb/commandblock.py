"""Command blocklist matching for krabb."""

import fnmatch
import re


def check_command_blocked(tool_name: str, command: str, patterns: list[str]) -> str | None:
    """Check if a tool call matches any blocked command pattern.

    Returns the matching pattern if blocked, None if allowed.

    Pattern types:
      - "tool:WebFetch"      — blocks an entire tool by name
      - "/regex/"            — Python regex matched against command string
      - "rm -rf *"           — glob pattern (contains * or ?)
      - "git push"           — prefix match (command starts with pattern)
    """
    if not patterns:
        return None

    for pattern in patterns:
        # Tool-level block: "tool:ToolName"
        if pattern.startswith("tool:"):
            blocked_tool = pattern[5:]
            if tool_name == blocked_tool:
                return pattern
            continue

        # Only match against command string for Bash tool
        if not command:
            continue

        # Regex: /pattern/
        if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
            regex = pattern[1:-1]
            try:
                if re.search(regex, command):
                    return pattern
            except re.error:
                continue

        # Glob: contains * or ?
        elif "*" in pattern or "?" in pattern:
            if fnmatch.fnmatch(command, pattern):
                return pattern

        # Prefix match
        else:
            if command.startswith(pattern):
                return pattern

    return None
