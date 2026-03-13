"""Domain blocklist matching for krabb."""

import re
from urllib.parse import urlparse


def extract_domain(url: str) -> str:
    """Extract the domain from a URL, handling missing schemes."""
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    domain = parsed.hostname or ""
    return domain.lower()


def check_domain(url: str, patterns: list[str]) -> bool:
    """Check if a URL matches any pattern in the blocklist.

    Pattern types:
      - "example.com"      — exact domain or any subdomain
      - "*.example.com"    — subdomains only (not example.com itself)
      - "/regex/"          — Python regex matched against the full URL
    """
    if not patterns:
        return True

    domain = extract_domain(url)

    for pattern in patterns:
        # Regex pattern: /pattern/
        if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
            regex = pattern[1:-1]
            try:
                if re.search(regex, url):
                    return True
            except re.error:
                continue

        # Wildcard: *.example.com
        elif pattern.startswith("*."):
            suffix = pattern[2:].lower()
            if domain.endswith("." + suffix):
                return True

        # Exact domain (also matches subdomains)
        # Normalize pattern to domain in case user pasted a full URL
        else:
            pat = extract_domain(pattern) if "/" in pattern or ":" in pattern else pattern.lower()
            if domain == pat or domain.endswith("." + pat):
                return True

    return False
