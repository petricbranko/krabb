"""Tests for krabb.blocklist."""

from krabb.blocklist import check_domain, extract_domain


class TestExtractDomain:
    def test_https_url(self):
        assert extract_domain("https://example.com/path") == "example.com"

    def test_http_url(self):
        assert extract_domain("http://example.com/path") == "example.com"

    def test_no_scheme(self):
        assert extract_domain("example.com/path") == "example.com"

    def test_subdomain(self):
        assert extract_domain("https://sub.example.com") == "sub.example.com"

    def test_port(self):
        assert extract_domain("https://example.com:8080/path") == "example.com"

    def test_uppercase(self):
        assert extract_domain("https://EXAMPLE.COM") == "example.com"


class TestCheckDomain:
    def test_exact_match(self):
        assert check_domain("https://example.com/page", ["example.com"]) is True

    def test_exact_match_subdomain(self):
        """Exact domain also matches subdomains."""
        assert check_domain("https://sub.example.com/page", ["example.com"]) is True

    def test_exact_no_match(self):
        assert check_domain("https://other.com/page", ["example.com"]) is False

    def test_wildcard_subdomain_match(self):
        assert check_domain("https://api.example.com", ["*.example.com"]) is True

    def test_wildcard_nested_subdomain(self):
        assert check_domain("https://a.b.example.com", ["*.example.com"]) is True

    def test_wildcard_no_match_base(self):
        """Wildcard *.example.com should NOT match example.com itself."""
        assert check_domain("https://example.com", ["*.example.com"]) is False

    def test_wildcard_no_match_other(self):
        assert check_domain("https://other.com", ["*.example.com"]) is False

    def test_regex_match(self):
        assert check_domain("https://api.example.com/v1", ["/example\\.com/"]) is True

    def test_regex_no_match(self):
        assert check_domain("https://other.com", ["/example\\.com/"]) is False

    def test_regex_full_url(self):
        assert check_domain("https://cdn.example.com/img.png", ["/\\.png$/"]) is True

    def test_empty_patterns_allows_all(self):
        assert check_domain("https://anything.com", []) is True

    def test_multiple_patterns(self):
        patterns = ["github.com", "*.npmjs.org"]
        assert check_domain("https://github.com/repo", patterns) is True
        assert check_domain("https://registry.npmjs.org/pkg", patterns) is True
        assert check_domain("https://evil.com", patterns) is False

    def test_case_insensitive(self):
        assert check_domain("https://EXAMPLE.COM/page", ["example.com"]) is True
