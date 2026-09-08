/**
 * The mockttp adapter.
 *
 * Contains no business logic — it translates between mockttp's request
 * objects and the engine's plain types, and wires the engine in as two
 * mockttp rules:
 *
 *   1. everything the engine matches gets a mocked response,
 *   2. everything else is passed through to the real server.
 *
 * Because the first rule's matcher consults the live engine, hot-reloading
 * the rules file needs no mockttp rules to be re-registered.
 */

import * as net from 'node:net'
import { setTimeout as sleep } from 'node:timers/promises'
import { getLocal, type CompletedRequest, type Mockttp } from 'mockttp'

import type { RuleEngine, Match } from './engine.js'
import type { Loader } from './loaders.js'
import type { MockResponse, ProxyRequest } from './models.js'

/**
 * Permissive CORS, reflecting the request's Origin so `credentials: true`
 * requests work. mockttp applies it to mocked *and* passed-through
 * responses, and answers OPTIONS preflights on its own.
 */
export const CORS_OPTIONS = {
  origin: true,
  credentials: true,
  methods: 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
} as const

/** Options for {@link startProxy}. */
export interface ProxyOptions {
  /** Interface to bind. Defaults to loopback only. */
  host?: string
  /** Port to listen on. Omit for a random free port. */
  port?: number
  /** CA key and certificate. Without it, only plain HTTP is intercepted. */
  https?: { keyPath: string; certPath: string }
  /** Called for every intercepted request. */
  onIntercept?: (url: string, response: MockResponse) => void
}

/** Flatten mockttp's header map into the engine's `Record<string, string>`. */
function flattenHeaders(headers: CompletedRequest['headers']): Record<string, string> {
  const flat: Record<string, string> = {}
  for (const [key, value] of Object.entries(headers)) {
    if (value === undefined) continue
    flat[key.toLowerCase()] = Array.isArray(value) ? value.join(', ') : value
  }
  return flat
}

/**
 * Convert a mockttp request into the engine's plain {@link ProxyRequest}.
 *
 * The one place mockttp's types cross into the engine. The body is decoded
 * (gzip, brotli) so rules match on what the client actually sent, falling back
 * to the raw buffer when it cannot be decoded.
 */
async function toProxyRequest(request: CompletedRequest): Promise<ProxyRequest> {
  const decoded = await request.body.getDecodedBuffer()
  return {
    url: request.url,
    method: request.method.toUpperCase(),
    headers: flattenHeaders(request.headers),
    body: decoded ?? request.body.buffer,
  }
}

/**
 * Carries the match found while testing the rule over to the handler that
 * builds the response, so the body is only parsed once per request.
 *
 * Entries are consumed by the handler that runs immediately afterwards; the
 * cap bounds the leak if a client disconnects in between.
 */
class PendingMatches {
  /** Matches awaiting their handler, keyed by mockttp's request id. */
  #entries = new Map<string, { request: ProxyRequest; match: Match }>()

  /** @param limit How many unclaimed matches to hold before evicting the oldest. */
  constructor(private readonly limit = 500) {}

  /** Store a match, evicting the oldest entry once the cap is reached. */
  set(id: string, value: { request: ProxyRequest; match: Match }): void {
    if (this.#entries.size >= this.limit) {
      const oldest = this.#entries.keys().next()
      if (!oldest.done) this.#entries.delete(oldest.value)
    }
    this.#entries.set(id, value)
  }

  /**
   * Remove and return a stored match.
   *
   * @returns The match, or `undefined` when the entry was evicted — the caller
   * then matches again rather than failing.
   */
  take(id: string): { request: ProxyRequest; match: Match } | undefined {
    const value = this.#entries.get(id)
    this.#entries.delete(id)
    return value
  }
}

/**
 * Start an intercepting proxy backed by `engine`.
 *
 * Binds loopback only unless `options.host` says otherwise, and intercepts
 * plain HTTP unless `options.https` supplies a CA — see {@link ensureCA}.
 *
 * @param engine Consulted live on every request, so rules may change while the
 * proxy runs without anything being re-registered.
 * @param loader Optional loader, polled for changes on every request.
 * @returns The running mockttp server; call `.stop()` to shut it down.
 *
 * @example Run on a random free port
 * ```ts
 * import { RuleEngine, startProxy } from 'pproxy'
 *
 * const engine = new RuleEngine().load([{ url_pattern: 'https://example.com/api/*' }])
 * const server = await startProxy(engine, null)
 *
 * server.port // the port that was chosen
 * await server.stop()
 * ```
 */
export async function startProxy(
  engine: RuleEngine,
  loader: Loader | null,
  options: ProxyOptions = {},
): Promise<Mockttp> {
  const server = getLocal({
    https: options.https,
    cors: CORS_OPTIONS,
    http2: 'fallback',
    recordTraffic: false,
    suggestChanges: false,
  })

  const pending = new PendingMatches()

  await server
    .forAnyRequest()
    .always()
    .matching(async (request) => {
      loader?.reloadIfChanged()
      const proxyReq = await toProxyRequest(request)
      const match = engine.findRule(proxyReq)
      if (match === null) return false
      pending.set(request.id, { request: proxyReq, match })
      return true
    })
    .thenCallback(async (request) => {
      const found = pending.take(request.id)
      const proxyReq = found?.request ?? (await toProxyRequest(request))
      const match = found?.match ?? engine.findRule(proxyReq)
      if (match === null) {
        // The rules changed between matching and responding; fail open with
        // a passthrough-shaped error rather than a stale mock.
        return { statusCode: 502, json: { error: 'pproxy: rule disappeared mid-request' } }
      }

      const mock = await engine.resolveResponse(match, proxyReq)
      options.onIntercept?.(proxyReq.url, mock)
      if (mock.delayMs > 0) await sleep(mock.delayMs)

      return {
        statusCode: mock.statusCode,
        headers: { 'content-type': mock.contentType, ...mock.headers },
        rawBody: engine.serializeBody(mock),
      }
    })

  await server.forAnyRequest().always().thenPassThrough()

  await listenOn(server, options.port, options.host ?? '127.0.0.1')
  return server
}

/**
 * Start the server bound to a single interface.
 *
 * mockttp calls `server.listen(port)` internally, which binds every
 * interface — for a MITM proxy on a laptop that is a downgrade from the
 * usual loopback default. Node's own `listen` accepts a host, so the bind
 * is redirected for the duration of startup.
 */
async function listenOn(server: Mockttp, port: number | undefined, host: string): Promise<void> {
  const original = net.Server.prototype.listen
  const listen = original as (this: net.Server, ...args: unknown[]) => net.Server
  net.Server.prototype.listen = function patched(this: net.Server, ...args: unknown[]) {
    return args.length === 1 && typeof args[0] === 'number'
      ? listen.call(this, args[0], host)
      : listen.apply(this, args)
  } as typeof original

  try {
    await server.start(port)
  } finally {
    net.Server.prototype.listen = original
  }
}
