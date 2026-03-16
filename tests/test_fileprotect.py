"""Tests for krabb.fileprotect."""

from krabb.fileprotect import check_file_protected


class TestCheckFileProtected:
    def test_empty_patterns(self):
        assert check_file_protected("/any/file.txt", []) is False

    def test_empty_path(self):
        assert check_file_protected("", ["*.env"]) is False

    def test_exact_path_match(self):
        assert check_file_protected("/Users/me/secrets.env", ["/Users/me/secrets.env"]) is True

    def test_exact_path_no_match(self):
        assert check_file_protected("/Users/me/other.txt", ["/Users/me/secrets.env"]) is False

    def test_glob_suffix(self):
        assert check_file_protected("/project/.env", ["*.env"]) is True
        assert check_file_protected("/project/config.env", ["*.env"]) is True

    def test_glob_suffix_no_match(self):
        assert check_file_protected("/project/env.txt", ["*.env"]) is False

    def test_glob_pattern(self):
        assert check_file_protected("/project/config.json", ["config.*"]) is True

    def test_directory_prefix(self):
        assert check_file_protected("/project/src/config/db.py", ["src/config/"]) is True
        assert check_file_protected("/project/src/config/nested/file.py", ["src/config/"]) is True

    def test_directory_prefix_no_match(self):
        assert check_file_protected("/project/src/main.py", ["src/config/"]) is False

    def test_basename_match(self):
        assert check_file_protected("/any/path/package-lock.json", ["package-lock.json"]) is True
        assert check_file_protected("/other/package-lock.json", ["package-lock.json"]) is True

    def test_basename_no_match(self):
        assert check_file_protected("/any/path/package.json", ["package-lock.json"]) is False

    def test_relative_path_match(self):
        assert check_file_protected("/project/src/secrets.ts", ["src/secrets.ts"]) is True

    def test_relative_path_no_match(self):
        assert check_file_protected("/project/lib/secrets.ts", ["src/secrets.ts"]) is False

    def test_multiple_patterns(self):
        patterns = ["*.env", "package-lock.json", "src/config/"]
        assert check_file_protected("/project/.env", patterns) is True
        assert check_file_protected("/x/package-lock.json", patterns) is True
        assert check_file_protected("/project/src/config/db.py", patterns) is True
        assert check_file_protected("/project/src/main.py", patterns) is False
