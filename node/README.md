# pproxy (Node)

The Node implementation of pproxy, built on
[mockttp](https://github.com/httptoolkit/mockttp) instead of mitmproxy.

It reads **the same `rules.json` / `rules.yaml`** as the Python package, so
the two are interchangeable — the file is the contract, and you can switch
backends without touching your rules.

## Why it exists

The Python package needs a Python environment on every machine that runs it,
and the mitmproxy runtime it borrows does not always ship the modules the
loaders want. This one installs with `npm` and carries its own runtime.

mockttp also covers, for free, several things the Python adapter builds by
hand or does without:

| Capability                           | Python                     | Node                          |
| ------------------------------------ | -------------------------- | ----------------------------- |
| CORS, including preflight            | hand-built headers         | one server option             |
| CORS on passed-through responses     | `response()` hook          | same option                   |
| CA certificate                       | `~/.mitmproxy`, mitm.it    | `pproxy cert install`         |
| HTTP/2, WebSockets, SOCKS, PAC       | mitmproxy                  | mockttp                       |
| Connection faults (reset/hang/close) | —                          | available in mockttp          |

What you give up is **mitmweb** — mitmproxy's traffic inspector UI — and
mitmproxy's transparent and WireGuard modes. If you inspect traffic in
mitmweb, keep using the Python backend.

## Install

```bash
cd node
npm install
npm run build
npm link          # puts `pproxy` on your PATH
```

## Usage

```bash
pproxy run ../rules.json                       # 127.0.0.1:8080
pproxy run ../rules.yaml -H 0.0.0.0 -p 9090 -v
pproxy check ../rules.json                     # validate and exit
```

`run` picks the format from the file extension (`.json`, `.yaml`, `.yml`)
and hot-reloads the file while running — an edit takes effect on the next
intercepted request, with no restart.

Unlike the Python `check`, this one reports the *specific* problem with a
rules file (a parse error, or which rule is missing `url_pattern`) rather
than reporting that nothing loaded.

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
binds every interface; pproxy narrows that, matching mitmproxy's default,
so an intercepting proxy on a laptop is not reachable from the network.

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

## Differences from the Python package

Both read the same rules files and match them identically — the glob matcher
is a port of Python's `fnmatch`, verified case by case, character classes
included. Where they differ:

- **`check` output.** The Node version reports the specific parse or rule
  error; the Python version reports that no rules loaded.
- **A malformed rule during hot-reload** keeps the last valid rules here.
  In Python it raises out of the request handler.
- **JSON response bodies** are serialized compactly (`{"a":1}`); Python's
  `json.dumps` writes `{"a": 1}`. Same JSON, different byte count.
- **Handlers may be async.** Python's decorator is synchronous.

## Development

```bash
npm test          # vitest — engine, loaders, CLI, and live proxy tests
npm run typecheck
```

The proxy tests start a real mockttp server and drive it over an actual
proxy connection, including a CONNECT tunnel with TLS terminated by the
generated CA.
