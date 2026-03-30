from models import Rule, MockResponse


class TestMockResponse:
    def test_defaults(self):
        r = MockResponse()
        assert r.status_code == 200
        assert r.body is None
        assert r.headers == {}
        assert r.content_type == "application/json"
        assert r.delay_ms == 0

    def test_custom_values(self):
        r = MockResponse(
            status_code=404,
            body={"error": "not found"},
            headers={"x-custom": "value"},
            content_type="text/plain",
            delay_ms=500,
        )
        assert r.status_code == 404
        assert r.body == {"error": "not found"}
        assert r.delay_ms == 500


class TestRule:
    def test_defaults(self):
        rule = Rule(pattern="*/api/*", response=MockResponse())
        assert rule.matcher == "glob"
        assert rule.name == ""

    def test_from_dict_minimal(self):
        rule = Rule.from_dict({"url_pattern": "*/api/*"})
        assert rule.pattern == "*/api/*"
        assert rule.matcher == "glob"
        assert rule.response.status_code == 200
        assert rule.response.body == {}
        assert rule.response.delay_ms == 0

    def test_from_dict_full(self):
        rule = Rule.from_dict({
            "url_pattern": r"/users/\d+",
            "matcher": "regex",
            "name": "user_detail",
            "status_code": 201,
            "body": {"id": 1},
            "headers": {"x-test": "yes"},
            "content_type": "text/plain",
            "delay_ms": 1000,
        })
        assert rule.pattern == r"/users/\d+"
        assert rule.matcher == "regex"
        assert rule.name == "user_detail"
        assert rule.response.status_code == 201
        assert rule.response.body == {"id": 1}
        assert rule.response.headers == {"x-test": "yes"}
        assert rule.response.content_type == "text/plain"
        assert rule.response.delay_ms == 1000
