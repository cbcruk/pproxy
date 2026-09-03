import inspect
import json
import logging
from typing import Any, Callable

from .models import Rule, MockResponse, Request
from .matching import get_matcher
from .graphql import GraphQLCondition, GraphQLRequest, parse_graphql

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

    @property
    def rules(self) -> list[Rule]:
        """The registered rules, in evaluation order."""
        return list(self._rules)

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
        graphql: GraphQLCondition | dict | None = None,
    ):
        """Decorator that registers a rule with a dynamic response body.

        The decorated function receives the matched URL and returns the
        response body. This is useful when the response depends on the
        request URL (e.g. extracting query parameters).

        A function declaring a second parameter also receives the parsed
        GraphQL request, so the mock can read the operation's variables.

        Args:
            pattern: URL pattern string.
            status_code: HTTP status code for the response.
            matcher: Matching strategy — "glob", "regex", or "exact".
            content_type: MIME type for the Content-Type header.
            graphql: Optional GraphQL condition, as a GraphQLCondition or the
                dict form used in rules files.

        Example::

            @engine.intercept("*/api/search/*", status_code=200)
            def handle_search(url: str) -> dict:
                query = url.split("q=")[-1]
                return {"results": [], "query": query}

        Example::

            @engine.intercept("*/graphql", graphql={"operation_name": "GetUser"})
            def handle_user(url: str, gql: GraphQLRequest) -> dict:
                return {"data": {"user": {"id": gql.variables["id"]}}}
        """
        if isinstance(graphql, dict):
            graphql = GraphQLCondition.from_dict(graphql)

        def decorator(fn: Callable[..., Any]):
            rule = Rule(
                pattern=pattern,
                matcher=matcher,
                name=fn.__name__,
                graphql=graphql,
                response=MockResponse(
                    status_code=status_code,
                    content_type=content_type,
                    body=None,
                    headers={},
                ),
            )
            rule._body_fn = fn  # type: ignore[attr-defined]
            rule._body_fn_arity = len(inspect.signature(fn).parameters)  # type: ignore[attr-defined]
            self._rules.append(rule)
            return fn

        return decorator

    # ── Matching ───────────────────────────────────────────

    def match(self, request: str | Request) -> MockResponse | None:
        """Find the first rule matching the request and return its response.

        Iterates through rules in registration order. A rule matches when its
        URL pattern matches and, for rules carrying a GraphQL condition, the
        request body parses as a GraphQL operation satisfying that condition.
        On the first match, all registered hooks are called, then the response
        is returned. If no rule matches, returns None (the request should pass
        through to the real server).

        The body is parsed at most once per call, and only when some rule
        actually asks for it.

        Args:
            request: The request to match. A bare string is treated as a URL,
                which is all a rule without a GraphQL condition looks at.

        Returns:
            A MockResponse if a rule matched, or None for pass-through.
        """
        if isinstance(request, str):
            request = Request(url=request)

        graphql_request: GraphQLRequest | None = None
        parsed = False

        for rule in self._rules:
            matcher = get_matcher(rule.matcher)
            if not matcher.match(request.url, rule.pattern):
                continue

            if rule.graphql is not None:
                if not parsed:
                    graphql_request = parse_graphql(request.body)
                    parsed = True
                if graphql_request is None or not rule.graphql.matches(graphql_request):
                    continue

            for hook in self._hooks:
                hook(request.url, rule)
            return self._resolve_response(rule, request, graphql_request)
        return None

    def _resolve_response(
        self,
        rule: Rule,
        request: Request,
        graphql_request: GraphQLRequest | None,
    ) -> MockResponse:
        body_fn = getattr(rule, "_body_fn", None)
        if body_fn is None:
            return rule.response

        if getattr(rule, "_body_fn_arity", 1) > 1:
            body = body_fn(request.url, graphql_request)
        else:
            body = body_fn(request.url)

        return MockResponse(
            status_code=rule.response.status_code,
            body=body,
            headers=rule.response.headers,
            content_type=rule.response.content_type,
        )

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
