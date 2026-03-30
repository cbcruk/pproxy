def build_cors_headers(request_headers: dict) -> dict[str, str]:
    """Build CORS response headers from the incoming request headers.

    Reflects the Origin header back (required for credentials: true).
    Falls back to "*" if no Origin is present.

    Args:
        request_headers: The incoming HTTP request headers as a dict.

    Returns:
        A dict of CORS response headers ready to merge into the response.
    """
    origin = request_headers.get("origin", "*")
    return {
        "access-control-allow-origin": origin,
        "access-control-allow-methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
        "access-control-allow-headers": request_headers.get(
            "access-control-request-headers", "*"
        ),
        "access-control-allow-credentials": "true",
    }
