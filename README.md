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

## Menu bar app (macOS)

Managing the proxy from a terminal gets tedious. pproxy ships a macOS
menu bar app (built on [rumps](https://github.com/jaredks/rumps)) that
starts and stops the proxy and opens the rules file for editing — all
from the menu bar.

Install the extra and run it:

```bash
pip install -e ".[tray]"
python -m tray            # uses intercept.py + rules.json in the cwd
python -m tray --script intercept.py --rules rules.json
```

The menu offers:

- **Start / Stop proxy** — runs `mitmdump -s intercept.py` as a child
  process and shows the running state in the menu bar title.
- **Edit rules…** — opens the rules file in your editor. Because the
  proxy hot-reloads that file (`JsonLoader.reload_if_changed`), edits go
  live on the next intercepted request — no restart.
- **Set editor…** — change the editor command.
- **Quit** — stops the proxy and exits.

The editor defaults to VS Code (`code`). Override it, in order of
precedence:

1. the `PPROXY_EDITOR` environment variable, or
2. the `editor` key in `~/.config/pproxy/config.json` (written by
   **Set editor…**).

```bash
PPROXY_EDITOR="subl" python -m tray   # use Sublime Text instead
```

The app is macOS-only. On other platforms, drive the proxy directly with
`mitmdump`/`mitmweb` as shown above and edit the rules file in any editor.

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
