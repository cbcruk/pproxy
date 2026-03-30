import re
from fnmatch import fnmatch
from typing import Protocol


class Matcher(Protocol):
    """Protocol that all matcher strategies must implement.

    To add a new matcher, create a class with a ``match`` method
    and register it in the ``MATCHERS`` dict below.
    """

    def match(self, url: str, pattern: str) -> bool:
        """Test whether a URL matches the given pattern.

        Args:
            url: The full request URL to test.
            pattern: The pattern string (format depends on the matcher).

        Returns:
            True if the URL matches the pattern.
        """
        ...


class GlobMatcher:
    """Matches URLs using shell-style wildcards (fnmatch).

    Examples:
        - ``*/api/users/*`` matches ``https://example.com/api/users/123``
        - ``*.json`` matches ``https://cdn.example.com/data.json``
    """

    def match(self, url: str, pattern: str) -> bool:
        return fnmatch(url, pattern)


class RegexMatcher:
    """Matches URLs using regular expressions.

    Compiled patterns are cached for performance.
    Uses ``re.search`` (partial match), not ``re.fullmatch``.

    Examples:
        - ``r"/users/\\d+$"`` matches URLs ending with ``/users/42``
        - ``r"api\\.(dev|staging)\\.example\\.com"`` matches specific subdomains
    """

    _cache: dict[str, re.Pattern] = {}

    def match(self, url: str, pattern: str) -> bool:
        if pattern not in self._cache:
            self._cache[pattern] = re.compile(pattern)
        return bool(self._cache[pattern].search(url))


class ExactMatcher:
    """Matches URLs by exact string equality.

    Example:
        - ``https://api.example.com/health`` matches only that exact URL.
    """

    def match(self, url: str, pattern: str) -> bool:
        return url == pattern


MATCHERS: dict[str, Matcher] = {
    "glob": GlobMatcher(),
    "regex": RegexMatcher(),
    "exact": ExactMatcher(),
}
"""Registry of available matchers. Add new matchers here."""


def get_matcher(name: str) -> Matcher:
    """Look up a matcher by name.

    Args:
        name: One of the keys in ``MATCHERS`` ("glob", "regex", "exact").

    Returns:
        The corresponding Matcher instance.

    Raises:
        ValueError: If the name is not registered in ``MATCHERS``.
    """
    if name not in MATCHERS:
        raise ValueError(f"Unknown matcher: {name!r}. Choose from {list(MATCHERS)}")
    return MATCHERS[name]
