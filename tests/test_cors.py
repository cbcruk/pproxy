from cors import build_cors_headers


class TestBuildCorsHeaders:
    def test_reflects_origin(self):
        headers = build_cors_headers({"origin": "https://example.com"})
        assert headers["access-control-allow-origin"] == "https://example.com"

    def test_fallback_to_wildcard(self):
        headers = build_cors_headers({})
        assert headers["access-control-allow-origin"] == "*"

    def test_reflects_request_headers(self):
        headers = build_cors_headers({
            "origin": "https://example.com",
            "access-control-request-headers": "Authorization, Content-Type",
        })
        assert headers["access-control-allow-headers"] == "Authorization, Content-Type"

    def test_default_request_headers(self):
        headers = build_cors_headers({"origin": "https://example.com"})
        assert headers["access-control-allow-headers"] == "*"

    def test_credentials_always_true(self):
        headers = build_cors_headers({})
        assert headers["access-control-allow-credentials"] == "true"

    def test_allows_common_methods(self):
        headers = build_cors_headers({})
        methods = headers["access-control-allow-methods"]
        for method in ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
            assert method in methods
