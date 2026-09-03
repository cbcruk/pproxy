import json

from pproxy.engine import RuleEngine
from pproxy.models import Rule, MockResponse, Request


class TestRuleRegistration:
    def test_add_rule(self):
        engine = RuleEngine()
        engine.add_rule(Rule(pattern="*/api/*", response=MockResponse()))
        assert engine.match("https://example.com/api/users") is not None

    def test_load_from_dicts(self):
        engine = RuleEngine().load([
            {"url_pattern": "*/api/*", "body": {"ok": True}},
        ])
        assert engine.match("https://example.com/api/users") is not None

    def test_load_replaces_existing_rules(self):
        engine = RuleEngine()
        engine.add_rule(Rule(pattern="*/old/*", response=MockResponse()))
        engine.load([{"url_pattern": "*/new/*"}])
        assert engine.match("https://example.com/old/path") is None
        assert engine.match("https://example.com/new/path") is not None

    def test_method_chaining(self):
        engine = RuleEngine()
        result = engine.add_rule(Rule(pattern="*", response=MockResponse()))
        assert result is engine


class TestMatching:
    def test_glob_match(self):
        engine = RuleEngine().load([{
            "url_pattern": "*/api/*",
            "status_code": 200,
            "body": {"ok": True},
        }])
        result = engine.match("https://example.com/api/users")
        assert result is not None
        assert result.status_code == 200
        assert result.body == {"ok": True}

    def test_no_match_returns_none(self):
        engine = RuleEngine().load([{
            "url_pattern": "*/api/*",
        }])
        assert engine.match("https://example.com/health") is None

    def test_regex_match(self):
        engine = RuleEngine()
        engine.add_rule(Rule(
            pattern=r"/users/\d+$",
            matcher="regex",
            response=MockResponse(body={"id": 1}),
        ))
        assert engine.match("https://api.example.com/users/42") is not None
        assert engine.match("https://api.example.com/users/abc") is None

    def test_exact_match(self):
        url = "https://example.com/api/health"
        engine = RuleEngine()
        engine.add_rule(Rule(
            pattern=url,
            matcher="exact",
            response=MockResponse(body={"status": "ok"}),
        ))
        assert engine.match(url) is not None
        assert engine.match(url + "/") is None

    def test_first_match_wins(self):
        engine = RuleEngine().load([
            {"url_pattern": "*/api/*", "body": {"first": True}},
            {"url_pattern": "*/api/users/*", "body": {"second": True}},
        ])
        result = engine.match("https://example.com/api/users/1")
        assert result.body == {"first": True}

    def test_empty_rules_returns_none(self):
        engine = RuleEngine()
        assert engine.match("https://example.com/anything") is None


class TestDecorator:
    def test_dynamic_body(self):
        engine = RuleEngine()

        @engine.intercept("*/search*")
        def handle(url: str) -> dict:
            return {"query": url.split("q=")[-1]}

        result = engine.match("https://api.example.com/search?q=hello")
        assert result is not None
        assert result.body == {"query": "hello"}

    def test_decorator_preserves_function(self):
        engine = RuleEngine()

        @engine.intercept("*/api/*")
        def my_handler(url: str) -> dict:
            return {}

        assert callable(my_handler)
        assert my_handler.__name__ == "my_handler"

    def test_decorator_with_options(self):
        engine = RuleEngine()

        @engine.intercept("*/api/*", status_code=201, matcher="glob", content_type="text/plain")
        def handle(url: str) -> str:
            return "created"

        result = engine.match("https://example.com/api/resource")
        assert result.status_code == 201
        assert result.content_type == "text/plain"
        assert result.body == "created"


class TestHooks:
    def test_hook_called_on_match(self):
        calls = []
        engine = RuleEngine().load([{"url_pattern": "*/api/*"}])
        engine.add_hook(lambda url, rule: calls.append((url, rule.pattern)))

        engine.match("https://example.com/api/users")
        assert len(calls) == 1
        assert calls[0] == ("https://example.com/api/users", "*/api/*")

    def test_hook_not_called_on_no_match(self):
        calls = []
        engine = RuleEngine().load([{"url_pattern": "*/api/*"}])
        engine.add_hook(lambda url, rule: calls.append(url))

        engine.match("https://example.com/health")
        assert len(calls) == 0

    def test_multiple_hooks(self):
        calls_a, calls_b = [], []
        engine = RuleEngine().load([{"url_pattern": "*"}])
        engine.add_hook(lambda url, rule: calls_a.append(url))
        engine.add_hook(lambda url, rule: calls_b.append(url))

        engine.match("https://example.com")
        assert len(calls_a) == 1
        assert len(calls_b) == 1


class TestSerializeBody:
    def setup_method(self):
        self.engine = RuleEngine()

    def test_dict_body(self):
        r = MockResponse(body={"key": "value"})
        assert self.engine.serialize_body(r) == b'{"key": "value"}'

    def test_list_body(self):
        r = MockResponse(body=[1, 2, 3])
        assert self.engine.serialize_body(r) == b'[1, 2, 3]'

    def test_str_body(self):
        r = MockResponse(body="hello")
        assert self.engine.serialize_body(r) == b"hello"

    def test_bytes_body(self):
        r = MockResponse(body=b"raw bytes")
        assert self.engine.serialize_body(r) == b"raw bytes"

    def test_none_body(self):
        r = MockResponse(body=None)
        assert self.engine.serialize_body(r) == b""

    def test_unicode_body(self):
        r = MockResponse(body={"name": "홍길동"})
        assert "홍길동" in self.engine.serialize_body(r).decode("utf-8")


class TestGraphQLMatching:
    def setup_method(self):
        self.engine = RuleEngine().load([
            {
                "name": "user",
                "url_pattern": "*/graphql",
                "graphql": {"operation_name": "GetUser"},
                "body": {"data": {"user": {"id": "1"}}},
            },
            {
                "name": "posts",
                "url_pattern": "*/graphql",
                "graphql": {"operation_name": "GetPosts"},
                "body": {"data": {"posts": []}},
            },
        ])

    def request(self, payload: dict) -> Request:
        return Request(
            url="https://example.com/graphql",
            method="POST",
            body=json.dumps(payload).encode(),
        )

    def test_picks_the_rule_for_the_operation(self):
        result = self.engine.match(self.request({
            "operationName": "GetPosts",
            "query": "query GetPosts { posts { id } }",
        }))
        assert result.body == {"data": {"posts": []}}

    def test_unknown_operation_passes_through(self):
        assert self.engine.match(self.request({
            "operationName": "GetComments",
            "query": "query GetComments { comments { id } }",
        })) is None

    def test_non_graphql_body_passes_through(self):
        assert self.engine.match(Request(
            url="https://example.com/graphql",
            method="POST",
            body=b"not json",
        )) is None

    def test_url_only_request_passes_through(self):
        assert self.engine.match("https://example.com/graphql") is None

    def test_variables_narrow_the_match(self):
        engine = RuleEngine().load([
            {
                "url_pattern": "*/graphql",
                "graphql": {"operation_name": "GetUser", "variables": {"id": "42"}},
                "body": {"data": {"user": {"id": "42"}}},
            },
            {
                "url_pattern": "*/graphql",
                "graphql": {"operation_name": "GetUser"},
                "status_code": 404,
                "body": {"errors": [{"message": "not found"}]},
            },
        ])
        query = "query GetUser($id: ID!) { user(id: $id) { id } }"

        hit = engine.match(Request(
            url="https://example.com/graphql",
            body=json.dumps({"query": query, "variables": {"id": "42"}}).encode(),
        ))
        assert hit.body == {"data": {"user": {"id": "42"}}}

        miss = engine.match(Request(
            url="https://example.com/graphql",
            body=json.dumps({"query": query, "variables": {"id": "7"}}).encode(),
        ))
        assert miss.status_code == 404

    def test_url_rule_without_condition_still_wins_by_order(self):
        engine = RuleEngine().load([
            {"url_pattern": "*/graphql", "body": {"data": None}},
            {
                "url_pattern": "*/graphql",
                "graphql": {"operation_name": "GetUser"},
                "body": {"data": {"user": {"id": "1"}}},
            },
        ])
        result = engine.match(self.request({"query": "query GetUser { user { id } }"}))
        assert result.body == {"data": None}

    def test_hook_receives_the_url(self):
        calls = []
        self.engine.add_hook(lambda url, rule: calls.append((url, rule.name)))
        self.engine.match(self.request({"query": "query GetUser { user { id } }"}))
        assert calls == [("https://example.com/graphql", "user")]

    def test_decorator_reads_variables(self):
        engine = RuleEngine()

        @engine.intercept("*/graphql", graphql={"operation_name": "GetUser"})
        def handle_user(url: str, gql) -> dict:
            return {"data": {"user": {"id": gql.variables["id"]}}}

        result = engine.match(Request(
            url="https://example.com/graphql",
            body=json.dumps({
                "query": "query GetUser($id: ID!) { user(id: $id) { id } }",
                "variables": {"id": "99"},
            }).encode(),
        ))
        assert result.body == {"data": {"user": {"id": "99"}}}
