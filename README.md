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

The repo ships an `intercept.py` entry point that loads `rules.json`:

```bash
mitmdump -s intercept.py      # headless
mitmweb  -s intercept.py      # with mitmproxy's web UI
```

`intercept.py` adds the project directory to `sys.path` (the layout is
flat) and builds the addon with `create_addon("rules.json")`, so it runs
straight from a checkout without installation.

> **Glob patterns and query strings.** The `glob` matcher is a full
> `fnmatch`, so a pattern without a trailing wildcard only matches the
> exact URL. To match real requests that carry a query string, end the
> pattern with `*` — e.g. `*/api/exam-rooms*` matches
> `…/api/exam-rooms?hospitalNo=42`.

> **HTTPS interception.** To intercept HTTPS you must trust mitmproxy's CA
> certificate once. Start the proxy, visit <http://mitm.it>, and follow
> the macOS instructions (add the cert to the System keychain and mark it
> trusted). Without this, HTTPS requests fail instead of being mocked.

## Menu bar (SwiftBar plugin, macOS)

Rather than shipping its own menu bar app, pproxy plugs into
[SwiftBar](https://swiftbar.app): SwiftBar owns the menu bar and runs the
plugin, and the plugin drives pproxy. Nothing beyond the standard library
is needed — the plugin shells out to the `tray` package.

Install SwiftBar, then symlink the plugin into your SwiftBar plugin
folder:

```bash
ln -s "$PWD/swiftbar/pproxy.5s.py" ~/Library/Application\ Support/SwiftBar/Plugins/
```

The plugin finds the project via its own real path (so the symlink still
locates `intercept.py` and `rules.json`), or via the `PPROXY_HOME`
environment variable. The menu offers:

- **Start / Stop proxy** — starts `mitmdump -s intercept.py` as a
  detached process (tracked by a pidfile in `~/.config/pproxy/`), points
  the macOS system proxy at `127.0.0.1:8080`, and shows the running state
  (🟢 / ⚪️) in the menu bar. Stopping clears the system proxy so normal
  internet access is restored.
- **Edit rules…** — opens the rules file in your editor. Because the
  proxy hot-reloads that file (`JsonLoader.reload_if_changed`), edits go
  live on the next intercepted request — no restart.
- **Log** — opens the proxy's output log.

System-proxy changes use `networksetup` on the auto-detected active
network service (Wi-Fi, etc.) and are *fail-soft*: if that can't be done,
it's logged and the proxy still runs — point your client at
`127.0.0.1:8080` manually.

The editor defaults to VS Code (`code`). Override it, in order of
precedence:

1. the `PPROXY_EDITOR` environment variable, or
2. the `editor` key in `~/.config/pproxy/config.json`.

```bash
PPROXY_EDITOR="subl" ...   # use Sublime Text instead
```

The plugin is macOS-only (SwiftBar and `networksetup`). On other
platforms, drive the proxy directly with `mitmdump`/`mitmweb` as shown
above and edit the rules file in any editor.

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
