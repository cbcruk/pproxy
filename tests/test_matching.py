import pytest

from matching import GlobMatcher, RegexMatcher, ExactMatcher, get_matcher


class TestGlobMatcher:
    def setup_method(self):
        self.m = GlobMatcher()

    def test_wildcard_match(self):
        assert self.m.match("https://example.com/api/users", "*/api/*")

    def test_wildcard_no_match(self):
        assert not self.m.match("https://example.com/health", "*/api/*")

    def test_exact_pattern(self):
        assert self.m.match("https://example.com/api", "https://example.com/api")

    def test_question_mark(self):
        assert self.m.match("https://example.com/api/v1", "*/api/v?")
        assert not self.m.match("https://example.com/api/v10", "*/api/v?")


class TestRegexMatcher:
    def setup_method(self):
        self.m = RegexMatcher()

    def test_digit_pattern(self):
        assert self.m.match("https://api.example.com/users/42", r"/users/\d+$")

    def test_digit_pattern_no_match(self):
        assert not self.m.match("https://api.example.com/users/abc", r"/users/\d+$")

    def test_partial_match(self):
        assert self.m.match("https://api.example.com/v1/search?q=hello", r"search\?q=")

    def test_cached_pattern_reuse(self):
        pattern = r"/test/\d+"
        self.m.match("https://example.com/test/1", pattern)
        assert pattern in self.m._cache
        self.m.match("https://example.com/test/2", pattern)


class TestExactMatcher:
    def setup_method(self):
        self.m = ExactMatcher()

    def test_exact_match(self):
        url = "https://example.com/api/health"
        assert self.m.match(url, url)

    def test_exact_no_match(self):
        assert not self.m.match(
            "https://example.com/api/health",
            "https://example.com/api/health/",
        )


class TestGetMatcher:
    def test_known_matchers(self):
        for name in ("glob", "regex", "exact"):
            assert get_matcher(name) is not None

    def test_unknown_matcher_raises(self):
        with pytest.raises(ValueError, match="Unknown matcher"):
            get_matcher("nonexistent")
