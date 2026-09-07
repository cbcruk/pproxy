import json

from pproxy.graphql import (
    GraphQLCondition,
    GraphQLRequest,
    contains_subset,
    extract_operation_name,
    parse_graphql,
)


def body(payload: dict) -> bytes:
    return json.dumps(payload).encode()


class TestParseGraphql:
    def test_full_payload(self):
        parsed = parse_graphql(body({
            "operationName": "GetUser",
            "query": "query GetUser($id: ID!) { user(id: $id) { id } }",
            "variables": {"id": "42"},
        }))
        assert parsed is not None
        assert parsed.operation_name == "GetUser"
        assert parsed.variables == {"id": "42"}

    def test_operation_name_recovered_from_query(self):
        parsed = parse_graphql(body({
            "query": "mutation UpdateUser($id: ID!) { updateUser(id: $id) { id } }",
        }))
        assert parsed is not None
        assert parsed.operation_name == "UpdateUser"

    def test_anonymous_operation_has_no_name(self):
        parsed = parse_graphql(body({"query": "{ viewer { id } }"}))
        assert parsed is not None
        assert parsed.operation_name == ""
        assert parsed.variables == {}

    def test_null_variables(self):
        parsed = parse_graphql(body({"query": "{ viewer { id } }", "variables": None}))
        assert parsed is not None
        assert parsed.variables == {}

    def test_empty_body(self):
        assert parse_graphql(b"") is None

    def test_non_json_body(self):
        assert parse_graphql(b"id=1&name=x") is None

    def test_json_without_query(self):
        assert parse_graphql(body({"id": 1})) is None

    def test_blank_query(self):
        assert parse_graphql(body({"query": "   "})) is None

    def test_batched_payload_is_not_recognized(self):
        assert parse_graphql(b'[{"query": "{ viewer { id } }"}]') is None

    def test_persisted_query_without_text_is_not_recognized(self):
        assert parse_graphql(body({
            "operationName": "GetUser",
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "abc"}},
        })) is None


class TestExtractOperationName:
    def test_query(self):
        assert extract_operation_name("query GetUser { user { id } }") == "GetUser"

    def test_subscription(self):
        assert extract_operation_name("subscription OnTick { tick }") == "OnTick"

    def test_leading_fragment(self):
        query = "fragment F on User { id }\nquery GetUser { user { ...F } }"
        assert extract_operation_name(query) == "GetUser"

    def test_anonymous(self):
        assert extract_operation_name("{ user { id } }") == ""


class TestContainsSubset:
    def test_exact_dict(self):
        assert contains_subset({"id": 1}, {"id": 1})

    def test_extra_keys_in_actual_are_ignored(self):
        assert contains_subset({"id": 1, "page": 2}, {"id": 1})

    def test_missing_key(self):
        assert not contains_subset({"page": 2}, {"id": 1})

    def test_value_mismatch(self):
        assert not contains_subset({"id": 2}, {"id": 1})

    def test_nested_dict(self):
        actual = {"filter": {"status": "active", "tag": "x"}}
        assert contains_subset(actual, {"filter": {"status": "active"}})
        assert not contains_subset(actual, {"filter": {"status": "done"}})

    def test_list_must_match_in_full(self):
        assert contains_subset({"ids": [1, 2]}, {"ids": [1, 2]})
        assert not contains_subset({"ids": [1, 2]}, {"ids": [1]})

    def test_empty_expected_matches_anything(self):
        assert contains_subset({"id": 1}, {})


class TestGraphQLCondition:
    def test_from_dict_defaults(self):
        condition = GraphQLCondition.from_dict({})
        assert condition.operation_name == ""
        assert condition.variables == {}

    def test_from_dict_null_variables(self):
        assert GraphQLCondition.from_dict({"variables": None}).variables == {}

    def test_operation_name_match(self):
        condition = GraphQLCondition(operation_name="GetUser")
        assert condition.matches(GraphQLRequest(operation_name="GetUser"))
        assert not condition.matches(GraphQLRequest(operation_name="GetPost"))

    def test_empty_condition_matches_any_operation(self):
        assert GraphQLCondition().matches(GraphQLRequest(operation_name="Anything"))

    def test_variables_match(self):
        condition = GraphQLCondition(operation_name="GetUser", variables={"id": "42"})
        assert condition.matches(
            GraphQLRequest(operation_name="GetUser", variables={"id": "42", "n": 1})
        )
        assert not condition.matches(
            GraphQLRequest(operation_name="GetUser", variables={"id": "7"})
        )

    def test_describe(self):
        assert GraphQLCondition().describe() == "*"
        assert GraphQLCondition(operation_name="GetUser").describe() == "GetUser"
        assert (
            GraphQLCondition(operation_name="GetUser", variables={"id": "42"}).describe()
            == 'GetUser {"id": "42"}'
        )
