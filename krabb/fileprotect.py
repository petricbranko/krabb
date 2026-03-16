"""File protection pattern matching for krabb."""

import fnmatch
import os


def check_file_protected(file_path: str, patterns: list[str]) -> bool:
    """Check if a file path matches any protected file pattern.

    Pattern types:
      - "/absolute/path/file.txt"  — exact path match
      - "*.env"                    — glob suffix (any file ending in .env)
      - "src/config/"              — directory prefix (anything under it)
      - "filename.json"            — basename match (matches anywhere)
    """
    if not patterns or not file_path:
        return False

    for pattern in patterns:
        # Directory prefix: pattern ends with /
        if pattern.endswith("/"):
            if f"/{pattern}" in f"/{file_path}/" or file_path.startswith(pattern):
                return True

        # Glob pattern: contains * or ?
        elif "*" in pattern or "?" in pattern:
            basename = os.path.basename(file_path)
            if fnmatch.fnmatch(basename, pattern) or fnmatch.fnmatch(file_path, pattern):
                return True

        # Absolute or relative path with separator: exact match or suffix match
        elif "/" in pattern or os.sep in pattern:
            if file_path == pattern or file_path.endswith("/" + pattern):
                return True

        # Basename match: just a filename
        else:
            if os.path.basename(file_path) == pattern:
                return True

    return False
