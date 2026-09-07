import json
import re
from dataclasses import dataclass, field
from typing import Any

OPERATION_NAME_RE = re.compile(
    r"\b(?:query|mutation|subscription)\s+([_A-Za-z][_0-9A-Za-z]*)"
)
"""Extracts the operation name from raw query text.

Used only when the request omits the ``operationName`` field, which many
GraphQL clients do for single-operation documents.
"""


@dataclass
class GraphQLRequest:
    """A parsed GraphQL request payload.

    Attributes:
        query: The raw GraphQL document text.
        operation_name: The operation name sent by the client, or the one
            recovered from ``query``. Empty for anonymous operations.
        variables: The variables map sent with the operation.
    """

    query: str = ""
    operation_name: str = ""
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphQLCondition:
    """An extra condition on a rule, evaluated against the request body.

    All non-empty fields must match (AND). An empty condition matches any
    parseable GraphQL request, which is a way to mock a whole endpoint.

    Attributes:
        operation_name: Required operation name. Empty means "any operation".
        variables: Variables that must be present in the request. Compared as
            a subset — extra variables in the request are ignored, and nested
            dicts are compared the same way.
    """

    operation_name: str = ""
    variables: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "GraphQLCondition":
        """Create a condition from the ``graphql`` block of a rule dict.

        Args:
            data: A dict with optional ``operation_name`` and ``variables`` keys.

        Returns:
            A new GraphQLCondition.
        """
        return cls(
            operation_name=data.get("operation_name", ""),
            variables=data.get("variables", {}) or {},
        )

    def matches(self, request: GraphQLRequest) -> bool:
        """Test whether a parsed GraphQL request satisfies this condition.

        Args:
            request: The parsed request payload.

        Returns:
            True if every configured field matches.
        """
        if self.operation_name and self.operation_name != request.operation_name:
            return False
        return contains_subset(request.variables, self.variables)

    def describe(self) -> str:
        """Render the condition as a one-line label for CLI output."""
        parts = [self.operation_name or "*"]
        if self.variables:
            parts.append(json.dumps(self.variables, ensure_ascii=False, sort_keys=True))
        return " ".join(parts)


def parse_graphql(body: bytes) -> GraphQLRequest | None:
    """Parse a GraphQL request body.

    Handles the ``application/json`` POST form — a single object with
    ``query``, and optionally ``operationName`` and ``variables``. Batched
    (array) payloads, ``GET`` query strings, ``application/graphql`` bodies,
    and persisted queries without query text are not recognized and yield
    None, so the request falls through to the real server.

    Args:
        body: The raw request body bytes.

    Returns:
        The parsed request, or None if the body is not a GraphQL operation.
    """
    if not body:
        return None
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        return None

    variables = payload.get("variables")
    if not isinstance(variables, dict):
        variables = {}

    operation_name = payload.get("operationName")
    if not isinstance(operation_name, str) or not operation_name:
        operation_name = extract_operation_name(query)

    return GraphQLRequest(
        query=query,
        operation_name=operation_name,
        variables=variables,
    )


def extract_operation_name(query: str) -> str:
    """Recover the operation name from raw GraphQL document text.

    Args:
        query: The GraphQL document.

    Returns:
        The first operation name found, or "" for an anonymous operation.
    """
    match = OPERATION_NAME_RE.search(query)
    return match.group(1) if match else ""


def contains_subset(actual: Any, expected: Any) -> bool:
    """Test whether ``expected`` is contained in ``actual``.

    Dicts are compared key by key, recursively; keys absent from ``expected``
    are ignored. Everything else is compared by equality, so lists must match
    in full.

    Args:
        actual: The value from the request.
        expected: The value configured on the rule.

    Returns:
        True if ``actual`` satisfies ``expected``.
    """
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(
            key in actual and contains_subset(actual[key], value)
            for key, value in expected.items()
        )
    return actual == expected
