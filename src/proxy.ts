/**
 * The mockttp adapter.
 *
 * Contains no business logic — it translates between mockttp's request
 * objects and the engine's plain types, and wires the engine in as three
 * mockttp rules:
 *
 *   1. a matched transform rule passes through and patches what comes back,
 *   2. a matched mocking rule gets a mocked response,
 *   3. everything else is passed through to the real server.
 *
 * The first two are one decision, not two: both matchers consult the same
 * engine result for the request, so "first match wins" still holds across a
 * rules file that mixes the two kinds. Because those matchers consult the live
 * engine, hot-reloading the rules file needs no mockttp rules to be
 * re-registered.
 */

import * as net from 'node:net'
import { setTimeout as sleep } from 'node:timers/promises'
import { getLocal, type CompletedRequest, type Headers, type Mockttp } from 'mockttp'

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
  /** Called for every mocked request. */
  onIntercept?: (url: string, response: MockResponse) => void
  /**
   * Called for every request whose response was patched, with the status the
   * real server returned. Separate from {@link onIntercept} because a
   * transform has no {@link MockResponse} to report.
   */
  onTransform?: (url: string, statusCode: number) => void
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

/** What the engine said about one request. */
interface Decision {
  /** The request in the engine's own types, with its body decoded once. */
  request: ProxyRequest
  /** The rule that matched, or `null` when the request passes through. */
  match: Match | null
}

/**
 * Holds each request's decision for the rest of that request.
 *
 * Two matchers and a handler may all ask about the same request — the
 * transform rule's matcher, the mocking rule's, and whichever handler runs —
 * and deciding once means the body is decoded and the rules walked once.
 *
 * What is stored is the in-flight promise rather than the settled decision,
 * because mockttp evaluates its rules' matchers concurrently. Storing the
 * result would let both matchers start before either had anything to find.
 *
 * An entry is dropped as soon as nothing else will ask: by the handler that
 * responds, or by the second matcher when nothing matched. The cap bounds the
 * leak if a client disconnects before that. A transform's handler only runs
 * once the real server has answered, so its entry is held for a whole round
 * trip.
 */
class PendingMatches {
  /** Decisions awaiting their handler, keyed by mockttp's request id. */
  #entries = new Map<string, Promise<Decision>>()

  /** @param limit How many unclaimed decisions to hold before evicting the oldest. */
  constructor(private readonly limit = 500) {}

  /** Store a decision, evicting the oldest entry once the cap is reached. */
  set(id: string, value: Promise<Decision>): void {
    if (this.#entries.size >= this.limit) {
      const oldest = this.#entries.keys().next()
      if (!oldest.done) this.#entries.delete(oldest.value)
    }
    this.#entries.set(id, value)
  }

  /** Return a stored decision without consuming it, for the second matcher. */
  peek(id: string): Promise<Decision> | undefined {
    return this.#entries.get(id)
  }

  /** Forget a decision nothing else will ask about. */
  drop(id: string): void {
    this.#entries.delete(id)
  }

  /**
   * Remove and return a stored decision.
   *
   * @returns The decision, or `undefined` when the entry was evicted — the
   * caller then matches again rather than failing.
   */
  take(id: string): Promise<Decision> | undefined {
    const value = this.#entries.get(id)
    this.#entries.delete(id)
    return value
  }
}

/**
 * Drop the headers that describe the body that was replaced.
 *
 * A patched body is fresh, uncompressed JSON, so the real server's
 * `content-encoding` would tell the client to gunzip plain text and its
 * `content-length` would be wrong. mockttp sets the correct framing itself
 * once these are gone.
 */
function withoutBodyFraming(headers: Headers): Headers {
  const dropped = new Set(['content-encoding', 'content-length', 'transfer-encoding'])
  return Object.fromEntries(
    Object.entries(headers).filter(([key]) => !dropped.has(key.toLowerCase())),
  )
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

  /**
   * Ask the engine about a request once, however many matchers enquire.
   *
   * The entry is stored before the first `await`, so a matcher that runs while
   * the decision is still being made waits on it instead of repeating it.
   */
  const decide = (request: CompletedRequest): Promise<Decision> => {
    const cached = pending.peek(request.id)
    if (cached) return cached
    const decision = toProxyRequest(request).then((proxyReq) => ({
      request: proxyReq,
      match: engine.findRule(proxyReq),
    }))
    pending.set(request.id, decision)
    return decision
  }

  await server
    .forAnyRequest()
    .always()
    .matching(async (request) => {
      // The first matcher to run, so the rules file is reloaded here — an edit
      // takes effect on the next request whether or not anything matches.
      loader?.reloadIfChanged()
      const { match } = await decide(request)
      return match !== null && match.rule.transform !== null
    })
    .thenPassThrough({
      beforeResponse: async (response, request) => {
        const found = await pending.take(request.id)
        const proxyReq = found?.request ?? (await toProxyRequest(request))
        const match = found?.match ?? engine.findRule(proxyReq)
        // The rules changed mid-request, or the body could not be decoded.
        // Either way, hand the client what the server actually said.
        if (match === null || match.rule.transform === null) return
        const decoded = await response.body.getDecodedBuffer()
        if (decoded === undefined) return

        const patched = engine.resolveTransform(match, proxyReq, decoded)
        options.onTransform?.(proxyReq.url, response.statusCode)
        if (match.rule.response.delayMs > 0) await sleep(match.rule.response.delayMs)

        return {
          statusCode: response.statusCode,
          headers: withoutBodyFraming(response.headers),
          body: patched,
        }
      },
    })

  await server
    .forAnyRequest()
    .always()
    .matching(async (request) => {
      const { match } = await decide(request)
      if (match === null) {
        // Nothing else will ask about this one — it is on its way to the
        // passthrough rule below — so release the entry now.
        pending.drop(request.id)
        return false
      }
      return match.rule.transform === null
    })
    .thenCallback(async (request) => {
      const found = await pending.take(request.id)
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
