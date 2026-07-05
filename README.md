# pproxy

A rewrite of the mitmproxy addon as a general-purpose library.
URL pattern-based response interception, testable independently without mitmproxy.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

### JSON rules file

```python
# intercept.py
from pproxy import create_addon
addon = create_addon("rules.json")
```

```json
[
  {
    "url_pattern": "*/api/users/*",
    "status_code": 200,
    "body": { "users": [] },
    "matcher": "glob"
  }
]
```

### YAML rules file

```python
from pproxy import RuleEngine, YamlLoader, MitmproxyAddon

engine = RuleEngine()
loader = YamlLoader("rules.yaml", engine)
loader.reload_if_changed()
addon = MitmproxyAddon(engine, loader)
```

```yaml
- url_pattern: '*/api/users/*'
  status_code: 200
  body:
    users: []
  matcher: glob
```

### Programmatic rules

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

### Decorator (dynamic response)

```python
@engine.intercept("*/api/search/*", status_code=200)
def handle_search(url: str) -> dict:
    query = url.split("q=")[-1]
    return {"results": [], "query": query}
```

### Response delay simulation

Set `delay_ms` to simulate slow APIs.

```python
engine.add_rule(Rule(
    pattern="*/api/slow/*",
    response=MockResponse(status_code=200, body={"ok": True}, delay_ms=2000),
))
```

```json
[
  {
    "url_pattern": "*/api/slow/*",
    "status_code": 200,
    "body": { "ok": true },
    "delay_ms": 2000
  }
]
```

### Hooks

```python
def log_intercept(url: str, rule: Rule) -> None:
    print(f"INTERCEPTED [{rule.name}] {url}")

engine.add_hook(log_intercept)
```

## Matchers

| Matcher          | Description        | Example                   |
| ---------------- | ------------------ | ------------------------- |
| `glob` (default) | fnmatch pattern    | `*/api/users/*`           |
| `regex`          | Regular expression | `r"/users/\d+$"`          |
| `exact`          | Exact string match | `https://example.com/api` |

## Running the proxy

```bash
mitmweb -s intercept.py
```

## GUI

Editing the rules file by hand gets tedious. pproxy ships a small
zero-dependency web app (Python stdlib only) for managing rules from the
browser — list, add, edit, delete, and reorder them (order matters, first
match wins).

The GUI never talks to the engine directly. It only edits the JSON rules
file, and because the proxy hot-reloads that file on every request
(`JsonLoader.reload_if_changed`), edits go live on the next intercepted
request — no restart:

```
┌─────────────┐   writes    ┌────────────┐   reads    ┌────────────┐
│  GUI (web)  │ ──────────▶ │ rules.json │ ─────────▶ │   engine   │
└─────────────┘             └────────────┘  hot-reload └────────────┘
```

### Embedded — one process (recommended)

`create_addon` embeds the GUI by default, so a single `mitmweb` runs both
the proxy and the GUI:

```python
# intercept.py
from pproxy import create_addon
addon = create_addon("rules.json")  # GUI on http://127.0.0.1:8765
```

```bash
mitmweb -s intercept.py
# proxy is up, and the rule GUI is at http://127.0.0.1:8765
```

Edit rules in the browser while the proxy runs — changes take effect on
the next request. The GUI starts and stops together with the proxy.

Customize or disable it:

```python
create_addon("rules.json", gui_port=9000)   # different port
create_addon("rules.json", gui=False)        # proxy only, no GUI
```

### Standalone

You can also run the GUI on its own — handy for editing rules without the
proxy running:

```bash
python -m gui rules.json --host 127.0.0.1 --port 8765
```

By default it binds to `127.0.0.1` (local access only).

## Testing

RuleEngine can be unit tested without mitmproxy:

```bash
pytest
```

```python
def test_glob_match():
    engine = RuleEngine().load([{
        "url_pattern": "*/api/*",
        "status_code": 200,
        "body": {"ok": True},
    }])
    assert engine.match("https://example.com/api/users") is not None
    assert engine.match("https://example.com/health") is None
```
