from dataclasses import dataclass, field
from typing import Any

from .graphql import GraphQLCondition


@dataclass
class MockResponse:
    """Intercepted response to return instead of the real server response.

    Attributes:
        status_code: HTTP status code (e.g. 200, 404, 500).
        body: Response body. Can be dict/list (auto-serialized to JSON),
            str, bytes, or None.
        headers: Additional HTTP response headers.
        content_type: MIME type for the Content-Type header.
        delay_ms: Artificial delay in milliseconds before sending the response.
            Useful for simulating slow APIs. 0 means no delay.
    """

    status_code: int = 200
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str = "application/json"
    delay_ms: int = 0


@dataclass
class Request:
    """An incoming HTTP request, in engine-native types.

    The adapter builds this from its own framework's request object so the
    engine never depends on mitmproxy. Rules that only look at the URL work
    with the defaults for every other field.

    Attributes:
        url: The full request URL.
        method: The HTTP method, uppercase.
        headers: The request headers, lowercase keys.
        body: The raw request body. Empty for requests without one.
    """

    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


@dataclass
class Rule:
    """A single URL interception rule.

    Binds a URL pattern to a mock response. When the engine encounters
    a request URL that matches ``pattern``, it returns ``response``
    instead of forwarding the request to the real server.

    Attributes:
        pattern: URL pattern string. Format depends on ``matcher``.
        response: The mock response to return when this rule matches.
        matcher: Matching strategy — "glob" (fnmatch), "regex", or "exact".
        name: Optional label for debugging and logging.
        graphql: Optional condition on the GraphQL request body. When set, the
            URL pattern and the condition must both match, which is how several
            rules can share one ``/graphql`` endpoint.
    """

    pattern: str
    response: MockResponse
    matcher: str = "glob"
    name: str = ""
    graphql: GraphQLCondition | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        """Create a Rule from a dict (typically loaded from JSON/YAML).

        Expected keys:
            - ``url_pattern`` (required): The URL pattern string.
            - ``matcher``: "glob" | "regex" | "exact". Defaults to "glob".
            - ``name``: Optional rule label.
            - ``status_code``: HTTP status code. Defaults to 200.
            - ``body``: Response body. Defaults to ``{}``.
            - ``headers``: Extra response headers. Defaults to ``{}``.
            - ``content_type``: MIME type. Defaults to "application/json".
            - ``delay_ms``: Response delay in ms. Defaults to 0.
            - ``graphql``: Optional ``{"operation_name": ..., "variables": ...}``
              block matched against the request body.

        Args:
            data: A dictionary with the keys described above.

        Returns:
            A new Rule instance.
        """
        graphql = data.get("graphql")
        return cls(
            pattern=data["url_pattern"],
            matcher=data.get("matcher", "glob"),
            name=data.get("name", ""),
            graphql=GraphQLCondition.from_dict(graphql) if graphql is not None else None,
            response=MockResponse(
                status_code=data.get("status_code", 200),
                body=data.get("body", {}),
                headers=data.get("headers", {}),
                content_type=data.get("content_type", "application/json"),
                delay_ms=data.get("delay_ms", 0),
            ),
        )
