# pproxy (Python) — archived

The original implementation: a [mitmproxy](https://mitmproxy.org) addon plus
the rule engine it grew out of. **It is no longer developed.** pproxy is now
the Node package at the repository root — see the [top-level
README](../../README.md).

Nothing here is imported by the current code. It is kept because it still
runs, and because two things are only available under mitmproxy:

- **mitmweb**, mitmproxy's traffic inspector UI
- **transparent and WireGuard capture**, for pulling traffic off a phone

If you need either, this still works. For everything else, use the Node
package — it needs no Python environment and generates its own CA.

## Running it

```bash
cd archive/python
pip install -e ".[proxy]"

mitmdump -s intercept.py      # headless
mitmweb  -s intercept.py      # with mitmproxy's web UI
```

`intercept.py` loads `../../rules.json` — the same file the Node proxy reads,
which is why the two were interchangeable in the first place. There is also a
CLI:

```bash
pproxy run ../../rules.json
pproxy check ../../rules.json
```

## Library use

The rule engine works without mitmproxy installed, which is what the tests
exercise.

```python
from pproxy import RuleEngine, Rule, MockResponse, MitmproxyAddon

engine = RuleEngine()
engine.add_rule(Rule(
    pattern=r"https://api\.example\.com/users/\d+",
    matcher="regex",
    name="user_detail",
    response=MockResponse(status_code=200, body={"id": 1, "name": "mock"}),
))
addon = MitmproxyAddon(engine)
```

A YAML rules file needs `pyyaml`, which the JSON path does not:

```python
from pproxy import RuleEngine, YamlLoader, MitmproxyAddon

engine = RuleEngine()
loader = YamlLoader("rules.yaml", engine)
loader.reload_if_changed()
addon = MitmproxyAddon(engine, loader)
```

Rules whose body depends on the request are registered with the `intercept`
decorator, which is synchronous here:

```python
from pproxy import GraphQLRequest

@engine.intercept("*/api/search/*", status_code=200)
def handle_search(url: str) -> dict:
    return {"results": [], "query": url.split("q=")[-1]}

@engine.intercept("*/graphql", graphql={"operation_name": "GetUser"})
def handle_user(url: str, gql: GraphQLRequest) -> dict:
    return {"data": {"user": {"id": gql.variables["id"]}}}
```

Hooks fire on every interception:

```python
def log_intercept(url: str, rule: Rule) -> None:
    print(f"INTERCEPTED [{rule.name}] {url}")

engine.add_hook(log_intercept)
```

The rules file format — matchers, `graphql`, `delay_ms` — is documented in the
[top-level README](../../README.md), and is identical for both.

## Tests

```bash
cd archive/python
pip install -e ".[proxy,dev]"
pytest
```

## What the Node package does differently

- **`check` output** names the specific parse or rule error; this one reports
  that no rules loaded.
- **A malformed rule during hot-reload** keeps the last valid rules there; here
  it raises out of the request handler.
- **JSON response bodies** are serialized compactly there (`{"a":1}`);
  `json.dumps` writes `{"a": 1}`. Same JSON, different byte count.
- **Handlers may be async** there. The decorator here is synchronous.
- **CORS** is one server option there; here the headers are built by hand in
  `src/pproxy/cors.py`.
- **The CA** is generated and installed by `pproxy cert install` there; here
  you trust mitmproxy's own CA via <http://mitm.it>.
