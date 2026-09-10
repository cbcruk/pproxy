/**
 * The rule engine.
 *
 * Ported from `archive/python/src/pproxy/engine.py`. Completely independent of mockttp —
 * it only deals with plain values, so it can be unit tested without
 * starting a proxy.
 */

import { getMatcher } from './matching.js'
import {
  GraphQLCondition,
  parseGraphql,
  type GraphQLConditionData,
  type GraphQLRequest,
} from './graphql.js'
import {
  proxyRequest,
  Rule,
  type Body,
  type BodyHandler,
  type MockResponse,
  type ProxyRequest,
  type RuleData,
} from './models.js'

/** Called on every interception with the matched URL and rule. */
export type InterceptHook = (url: string, rule: Rule) => void

/** Options for {@link RuleEngine.intercept}. */
export interface InterceptOptions {
  /** Status code to respond with; defaults to 200. */
  statusCode?: number
  /** Matching strategy name; defaults to `"glob"`. */
  matcher?: string
  /** Content-Type; defaults to `"application/json"`. */
  contentType?: string
  /** Extra response headers. */
  headers?: Record<string, string>
  /** Artificial delay in milliseconds; defaults to 0. */
  delayMs?: number
  /**
   * Extra condition on the GraphQL request body. Accepts either the in-memory
   * {@link GraphQLCondition} or the snake_case rules-file form.
   */
  graphql?: GraphQLCondition | GraphQLConditionData | null
}

/** A rule that matched, with the parsed GraphQL body if one was needed. */
export interface Match {
  /** The first rule that matched, in registration order. */
  rule: Rule
  /**
   * The parsed request body, but only when the rule carried a GraphQL
   * condition. `null` for a plain URL rule, which never reads the body.
   */
  graphql: GraphQLRequest | null
}

/**
 * Matches requests against registered rules.
 *
 * Rules are evaluated in registration order — first match wins.
 */
export class RuleEngine {
  /** Registered rules, in evaluation order. First match wins. */
  #rules: Rule[] = []
  /** Hooks fired once per interception, in registration order. */
  #hooks: InterceptHook[] = []

  /** The registered rules, in evaluation order. */
  get rules(): Rule[] {
    return [...this.#rules]
  }

  // ── Rule registration ──────────────────────────────────

  /** Register a single rule. */
  addRule(rule: Rule): this {
    this.#rules.push(rule)
    return this
  }

  /**
   * Replace all rules from a rules-file array.
   *
   * This is the entry point used by the loaders. It **replaces** the existing
   * rules rather than appending.
   *
   * @throws If the input is not an array, or a rule is missing `url_pattern`.
   */
  load(rules: RuleData[]): this {
    if (!Array.isArray(rules)) {
      throw new Error(`rules must be a list, got ${rules === null ? 'null' : typeof rules}`)
    }
    this.#rules = rules.map((rule) => Rule.fromData(rule))
    return this
  }

  /** Register a hook that fires on every successful match. */
  addHook(hook: InterceptHook): void {
    this.#hooks.push(hook)
  }

  /**
   * Register a rule whose body is computed per request.
   *
   * The handler receives the matched URL and, for a rule carrying a GraphQL
   * condition, the parsed request — which is how a mock reads the operation's
   * variables.
   *
   * Unlike {@link load}, this appends: a rule registered here sits after
   * everything already registered, and first match wins.
   *
   * @example Echo a variable back from a GraphQL mock
   * ```ts
   * import { RuleEngine } from 'pproxy'
   *
   * const engine = new RuleEngine()
   *
   * engine.intercept(
   *   'https://example.com/graphql',
   *   (url, gql) => ({ data: { user: { id: gql?.variables['id'] } } }),
   *   { graphql: { operation_name: 'GetUser' } },
   * )
   * ```
   */
  intercept(pattern: string, handler: BodyHandler, options: InterceptOptions = {}): this {
    const condition =
      options.graphql instanceof GraphQLCondition
        ? options.graphql
        : options.graphql != null
          ? GraphQLCondition.fromData(options.graphql)
          : null

    const rule = new Rule({
      pattern,
      matcher: options.matcher ?? 'glob',
      name: handler.name || '',
      graphql: condition,
      response: {
        statusCode: options.statusCode ?? 200,
        contentType: options.contentType ?? 'application/json',
        headers: options.headers ?? {},
        delayMs: options.delayMs ?? 0,
        body: null,
      },
    })
    rule.bodyHandler = handler
    this.#rules.push(rule)
    return this
  }

  // ── Matching ───────────────────────────────────────────

  /**
   * Find the first rule matching the request, without firing hooks or
   * building a response.
   *
   * The body is parsed at most once per call, and only when some rule
   * actually asks for it.
   */
  findRule(request: string | ProxyRequest): Match | null {
    const req = typeof request === 'string' ? proxyRequest(request) : request

    let graphql: GraphQLRequest | null = null
    let parsed = false

    for (const rule of this.#rules) {
      if (!getMatcher(rule.matcher).match(req.url, rule.pattern)) continue

      if (rule.graphql !== null) {
        if (!parsed) {
          graphql = parseGraphql(req.body)
          parsed = true
        }
        if (graphql === null || !rule.graphql.matches(graphql)) continue
      }

      return { rule, graphql }
    }
    return null
  }

  /**
   * Find the first matching rule and return its response.
   *
   * Returns `null` when nothing matched, meaning the request should pass
   * through to the real server.
   */
  async match(request: string | ProxyRequest): Promise<MockResponse | null> {
    const req = typeof request === 'string' ? proxyRequest(request) : request
    const found = this.findRule(req)
    return found === null ? null : this.resolveResponse(found, req)
  }

  /**
   * Build the response for a match, invoking the rule's body handler if it
   * has one.
   *
   * This is where hooks fire — the point at which a match is actually acted
   * on — so they run once per interception whether the caller went through
   * {@link match} or matched and resolved in two steps, as the proxy does.
   */
  async resolveResponse(match: Match, request: ProxyRequest): Promise<MockResponse> {
    const { rule, graphql } = match
    for (const hook of this.#hooks) hook(request.url, rule)
    if (!rule.bodyHandler) return rule.response
    return { ...rule.response, body: await rule.bodyHandler(request.url, graphql) }
  }

  /**
   * Patch the real server's response for a matched transform rule.
   *
   * The counterpart to {@link resolveResponse} for rules that carry a
   * {@link Rule.transform} rather than a body, and where hooks fire for them —
   * once per interception, as on the mocking path.
   *
   * Fails open: a body that is empty or is not JSON comes back untouched,
   * because a rule that cannot be applied should not corrupt a response the
   * client would otherwise have received intact.
   *
   * @param body The real response body, already decoded.
   * @returns The patched bytes, or `body` itself when nothing was applied.
   *
   * @example Patch a field without mocking the whole response
   * ```ts
   * import { RuleEngine, proxyRequest } from 'pproxy'
   *
   * const engine = new RuleEngine().load([
   *   {
   *     url_pattern: 'https://example.com/graphql',
   *     merge_patch: { data: { user: { name: 'patched' } } },
   *   },
   * ])
   *
   * const request = proxyRequest('https://example.com/graphql')
   * const match = engine.findRule(request)!
   * const patched = engine.resolveTransform(match, request, Buffer.from('{"data":{"user":{"id":1}}}'))
   *
   * patched.toString() // {"data":{"user":{"id":1,"name":"patched"}}}
   * ```
   */
  resolveTransform(match: Match, request: ProxyRequest, body: Buffer): Buffer {
    const { rule } = match
    for (const hook of this.#hooks) hook(request.url, rule)
    if (rule.transform === null) return body

    const text = body.toString('utf8')
    if (!text.trim()) return body

    let parsed: unknown
    try {
      parsed = JSON.parse(text)
    } catch {
      return body
    }
    return Buffer.from(JSON.stringify(rule.transform.apply(parsed)), 'utf8')
  }

  // ── Serialization ──────────────────────────────────────

  /**
   * Convert a response body to the bytes sent over the wire.
   *
   * Objects and arrays are JSON-encoded, strings are UTF-8 encoded, buffers
   * pass through, and `null` becomes an empty body.
   */
  serializeBody(response: MockResponse): Buffer {
    return serializeBody(response.body)
  }
}

/**
 * Convert a response body to the bytes sent over the wire.
 *
 * The standalone form of {@link RuleEngine.serializeBody}, for callers holding
 * a body rather than a whole response.
 *
 * @returns JSON for objects and arrays, UTF-8 for strings, the buffer itself
 * for a buffer, and an empty buffer for `null`.
 */
export function serializeBody(body: Body): Buffer {
  if (body === null || body === undefined) return Buffer.alloc(0)
  if (Buffer.isBuffer(body)) return body
  if (typeof body === 'string') return Buffer.from(body, 'utf8')
  return Buffer.from(JSON.stringify(body), 'utf8')
}
