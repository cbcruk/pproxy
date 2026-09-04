/**
 * The rule engine.
 *
 * Ported from `src/pproxy/engine.py`. Completely independent of mockttp —
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
  statusCode?: number
  matcher?: string
  contentType?: string
  headers?: Record<string, string>
  delayMs?: number
  graphql?: GraphQLCondition | GraphQLConditionData | null
}

/** A rule that matched, with the parsed GraphQL body if one was needed. */
export interface Match {
  rule: Rule
  graphql: GraphQLRequest | null
}

/**
 * Matches requests against registered rules.
 *
 * Rules are evaluated in registration order — first match wins.
 */
export class RuleEngine {
  #rules: Rule[] = []
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
   * ```ts
   * engine.intercept('*​/graphql', (url, gql) => ({
   *   data: { user: { id: gql?.variables.id } },
   * }), { graphql: { operation_name: 'GetUser' } })
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

/** @see RuleEngine.serializeBody */
export function serializeBody(body: Body): Buffer {
  if (body === null || body === undefined) return Buffer.alloc(0)
  if (Buffer.isBuffer(body)) return body
  if (typeof body === 'string') return Buffer.from(body, 'utf8')
  return Buffer.from(JSON.stringify(body), 'utf8')
}
