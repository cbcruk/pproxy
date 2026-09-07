# pproxy

Poorman's proxy — a URL pattern-based HTTP response interceptor. Point your
client at it, and requests matching a rule get a mocked response instead of
reaching the real server. Everything else passes through untouched.

Built on [mockttp](https://github.com/httptoolkit/mockttp): it installs with
`npm`, carries its own runtime, and generates its own CA, so intercepting
HTTPS is one command rather than a certificate scavenger hunt.

> The original Python/mitmproxy implementation lives in
> [`archive/python/`](archive/python/README.md). It still runs and still
> reads the same rules file, but it is no longer developed — reach for it
> only if you need **mitmweb** (mitmproxy's traffic inspector UI) or
> transparent/WireGuard capture.

## Install

```bash
npm install
npm run build
npm link          # puts `pproxy` on your PATH
```

## Usage

```bash
pproxy run rules.json                       # 127.0.0.1:8080
pproxy run rules.yaml -H 0.0.0.0 -p 9090 -v
pproxy check rules.json                     # validate and exit
```

`run` picks the format from the file extension (`.json`, `.yaml`, `.yml`) and
hot-reloads the file while running — an edit takes effect on the next
intercepted request, with no restart. A malformed rule during a reload keeps
the last valid rules rather than taking the proxy down.

`check` validates without starting anything and reports the *specific*
problem — a parse error, or which rule is missing `url_pattern`:

```
  glob  */api/users/* → 200 (users)
  regex /orders/\d+ → 201
2 rules OK
```

It exits non-zero on a missing file, a parse error, a rule without
`url_pattern`, or an unknown matcher.

### HTTPS

Intercepting HTTPS means terminating TLS, so the client has to trust a
certificate pproxy signs. The CA is generated on the first `run` and kept in
`~/.config/pproxy/`, so it only has to be trusted once:

```bash
pproxy cert path        # where the certificate lives
pproxy cert install     # add it to the macOS system trust store (asks for sudo)
pproxy cert uninstall   # remove it again
```

On other platforms, `cert path` prints the file to trust by hand. Pass
`--http-only` to `run` to skip HTTPS entirely.

### Binding

The proxy listens on `127.0.0.1` unless you pass `--host`. mockttp itself
binds every interface; pproxy narrows that, so an intercepting proxy on a
laptop is not reachable from the network.

## Rules

A rules file is a list of rules, in JSON or YAML. The first match wins.

```json
[
  {
    "name": "example_mock",
    "url_pattern": "*/api/example*",
    "matcher": "glob",
    "status_code": 200,
    "body": { "message": "mocked by pproxy", "items": [] }
  }
]
```

```yaml
- url_pattern: '*/api/users/*'
  status_code: 200
  body:
    users: []
  matcher: glob
```

### Matchers

| Matcher          | Description        | Example                   |
| ---------------- | ------------------ | ------------------------- |
| `glob` (default) | fnmatch pattern    | `*/api/users/*`           |
| `regex`          | Regular expression | `/users/\d+$`             |
| `exact`          | Exact string match | `https://example.com/api` |

> **Glob patterns and query strings.** The `glob` matcher is a full
> `fnmatch`, so a pattern without a trailing wildcard only matches the exact
> URL. To match real requests that carry a query string, end the pattern
> with `*` — e.g. `*/api/exam-rooms*` matches
> `…/api/exam-rooms?hospitalNo=42`.

### GraphQL

GraphQL sends every operation to the same endpoint, so a URL pattern alone
cannot tell `GetUser` from `GetPosts`. Add a `graphql` block and the rule
matches only when the request body carries that operation.

```json
[
  {
    "name": "user_detail",
    "url_pattern": "*/graphql",
    "graphql": { "operation_name": "GetUser" },
    "status_code": 200,
    "body": { "data": { "user": { "id": "1", "name": "mock" } } }
  }
]
```

`variables` narrows a rule further. It is compared as a subset, so only the
listed keys have to match — put the specific rule first, since the first
match wins.

```json
[
  {
    "url_pattern": "*/graphql",
    "graphql": { "operation_name": "GetUser", "variables": { "id": "42" } },
    "body": { "data": { "user": { "id": "42" } } }
  },
  {
    "url_pattern": "*/graphql",
    "graphql": { "operation_name": "GetUser" },
    "body": { "errors": [{ "message": "not found" }] }
  }
]
```

`operation_name` is optional — an empty `"graphql": {}` block matches any
GraphQL operation on that URL. When a client omits `operationName`, the name
is recovered from the query text, so only truly anonymous operations
(`{ viewer { id } }`) match on an empty condition alone.

GraphQL reports errors with HTTP 200 and an `errors` array, so mock a failure
by setting `body` rather than `status_code`.

Only the `application/json` POST form is recognized. These fall through to
the real server untouched:

- batched requests (a JSON array of operations)
- `GET` requests carrying the query in the query string
- `application/graphql` bodies and multipart file uploads
- persisted queries (APQ) that send only a hash, with no query text

### Response delay

Set `delay_ms` to simulate a slow API.

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

## Library use

The rule engine is independent of the proxy, so rules can be unit tested
without starting anything:

```ts
import { RuleEngine } from 'pproxy'

const engine = new RuleEngine().load([
  { url_pattern: '*/api/users/*', status_code: 200, body: { users: [] } },
])

await engine.match('https://example.com/api/users/1') // → MockResponse
await engine.match('https://example.com/health')      // → null
```

Rules whose body depends on the request are registered with `intercept`,
which also accepts async handlers:

```ts
engine.intercept('*/api/search*', (url) => ({ query: new URL(url).searchParams.get('q') }))

engine.intercept(
  '*/graphql',
  (_url, gql) => ({ data: { user: { id: gql?.variables['id'] } } }),
  { graphql: { operation_name: 'GetUser' } },
)
```

To run an engine against real traffic:

```ts
import { RuleEngine, startProxy, ensureCA } from 'pproxy'

const ca = await ensureCA()
const server = await startProxy(engine, null, { port: 8080, https: ca })
```

## Menu bar (SwiftBar plugin, macOS)

Rather than shipping its own menu bar app, pproxy plugs into
[SwiftBar](https://swiftbar.app): SwiftBar owns the menu bar and runs the
plugin, and the plugin drives pproxy. Nothing beyond the Python standard
library is needed — the plugin shells out to the `tray` package next to it,
so there is no install step.

Install SwiftBar, then symlink the plugin into your SwiftBar plugin folder:

```bash
ln -s "$PWD/swiftbar/pproxy.5s.py" ~/Library/Application\ Support/SwiftBar/Plugins/
```

The plugin finds the project via its own real path (so the symlink still
locates `rules.json`), or via the `PPROXY_HOME` environment variable. The
menu offers:

- **Start / Stop proxy** — runs `pproxy run rules.json` as a detached process
  (tracked by a pidfile in `~/.config/pproxy/`), points the macOS system
  proxy at `127.0.0.1:8080`, and shows the running state (🟢 / ⚪️) in the
  menu bar. Stopping clears the system proxy so normal internet access is
  restored.
- **Edit rules…** — opens the rules file in your editor. Because the proxy
  hot-reloads that file, edits go live on the next intercepted request — no
  restart.
- **Log** — opens the proxy's output log.

`pproxy` has to be on the PATH for this (`npm link` above), or be named
explicitly with `proxy_command`.

System-proxy changes use `networksetup` on the auto-detected active network
service (Wi-Fi, etc.) and are *fail-soft*: if that can't be done, it's logged
and the proxy still runs — point your client at `127.0.0.1:8080` manually.

Settings live in `~/.config/pproxy/config.json`, and each one can be
overridden by an environment variable:

| Setting         | Environment variable | Default  | Meaning                                   |
| --------------- | -------------------- | -------- | ----------------------------------------- |
| `editor`        | `PPROXY_EDITOR`      | `code`   | editor for **Edit rules…**                |
| `proxy_command` | `PPROXY_COMMAND`     | `pproxy` | override the executable that gets spawned |

```bash
PPROXY_EDITOR="subl" ...            # use Sublime Text instead
PPROXY_COMMAND="npx pproxy" ...     # skip `npm link`
```

The plugin is macOS-only (SwiftBar and `networksetup`). On other platforms,
run `pproxy run rules.json` directly and edit the rules file in any editor.

## Development

```bash
npm test          # vitest — engine, loaders, CLI, and live proxy tests
npm run typecheck
```

The proxy tests start a real mockttp server and drive it over an actual proxy
connection, including a CONNECT tunnel with TLS terminated by the generated
CA.

The SwiftBar plugin has its own suite:

```bash
cd swiftbar && pytest
```

## Layout

```
src/            the proxy and rule engine (TypeScript)
test/           its tests
rules.json      example rules, and what the menu bar plugin drives
swiftbar/       macOS menu bar plugin + the `tray` package it shells out to
archive/python/ the original mitmproxy implementation, no longer developed
```
