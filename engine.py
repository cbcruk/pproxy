import json
import logging
from typing import Any, Callable

from models import Rule, MockResponse
from matching import get_matcher

logger = logging.getLogger("pproxy")

InterceptHook = Callable[[str, Rule], None]
"""Type alias for hook functions called on every interception.
Receives (url, matched_rule) as arguments."""


class RuleEngine:
    """Core rule engine that matches URLs against registered rules.

    This class is completely independent of mitmproxy — it only deals
    with plain strings and dataclasses. The mitmproxy adapter wraps
    this engine and translates between mitmproxy types and engine types.

    Rules are evaluated in registration order (first match wins).
    """

    def __init__(self) -> None:
        self._rules: list[Rule] = []
        self._hooks: list[InterceptHook] = []

    # ── Rule registration ──────────────────────────────────

    def add_rule(self, rule: Rule) -> "RuleEngine":
        """Register a single rule.

        Args:
            rule: The Rule to add.

        Returns:
            self, for method chaining.
        """
        self._rules.append(rule)
        return self

    def load(self, rules: list[dict]) -> "RuleEngine":
        """Replace all rules from a list of dicts.

        This is the main entry point used by loaders (JsonLoader, YamlLoader).
        Calling this **replaces** all existing rules rather than appending.

        Args:
            rules: List of rule dicts (see ``Rule.from_dict`` for expected keys).

        Returns:
            self, for method chaining.
        """
        self._rules = [Rule.from_dict(r) for r in rules]
        return self

    def add_hook(self, hook: InterceptHook) -> None:
        """Register a hook that fires on every successful match.

        Args:
            hook: A callable ``(url: str, rule: Rule) -> None``.
        """
        self._hooks.append(hook)

    # ── Decorator API ──────────────────────────────────────

    def intercept(
        self,
        pattern: str,
        *,
        status_code: int = 200,
        matcher: str = "glob",
        content_type: str = "application/json",
    ):
        """Decorator that registers a rule with a dynamic response body.

        The decorated function receives the matched URL and returns the
        response body. This is useful when the response depends on the
        request URL (e.g. extracting query parameters).

        Args:
            pattern: URL pattern string.
            status_code: HTTP status code for the response.
            matcher: Matching strategy — "glob", "regex", or "exact".
            content_type: MIME type for the Content-Type header.

        Example::

            @engine.intercept("*/api/search/*", status_code=200)
            def handle_search(url: str) -> dict:
                query = url.split("q=")[-1]
                return {"results": [], "query": query}
        """

        def decorator(fn: Callable[[str], Any]):
            rule = Rule(
                pattern=pattern,
                matcher=matcher,
                name=fn.__name__,
                response=MockResponse(
                    status_code=status_code,
                    content_type=content_type,
                    body=None,
                    headers={},
                ),
            )
            rule._body_fn = fn  # type: ignore[attr-defined]
            self._rules.append(rule)
            return fn

        return decorator

    # ── Matching ───────────────────────────────────────────

    def match(self, url: str) -> MockResponse | None:
        """Find the first rule matching the URL and return its response.

        Iterates through rules in registration order. On the first match,
        all registered hooks are called, then the response is returned.
        If no rule matches, returns None (the request should pass through
        to the real server).

        Args:
            url: The full request URL to match against.

        Returns:
            A MockResponse if a rule matched, or None for pass-through.
        """
        for rule in self._rules:
            matcher = get_matcher(rule.matcher)
            if matcher.match(url, rule.pattern):
                for hook in self._hooks:
                    hook(url, rule)
                return self._resolve_response(rule, url)
        return None

    def _resolve_response(self, rule: Rule, url: str) -> MockResponse:
        body_fn = getattr(rule, "_body_fn", None)
        if body_fn is not None:
            return MockResponse(
                status_code=rule.response.status_code,
                body=body_fn(url),
                headers=rule.response.headers,
                content_type=rule.response.content_type,
            )
        return rule.response

    # ── Serialization ──────────────────────────────────────

    def serialize_body(self, response: MockResponse) -> bytes:
        """Convert a MockResponse body to bytes for the HTTP response.

        Handles three body types:
            - dict/list → JSON-encoded bytes (UTF-8)
            - str → UTF-8 encoded bytes
            - bytes/None → returned as-is (None becomes empty bytes)

        Args:
            response: The MockResponse whose body to serialize.

        Returns:
            The body as bytes, ready to send over the wire.
        """
        if isinstance(response.body, (dict, list)):
            return json.dumps(response.body, ensure_ascii=False).encode()
        if isinstance(response.body, str):
            return response.body.encode()
        return response.body or b""
