/**
 * Engine-native request/response/rule types.
 *
 * Ported from `archive/python/src/pproxy/models.py`. Field names in a *rules file* stay
 * snake_case so a single `rules.json` drives either implementation; the
 * in-memory types use the JavaScript convention.
 */

import { GraphQLCondition, type GraphQLConditionData, type GraphQLRequest } from './graphql.js'

/** A response body as it can be written in a rules file or returned by a handler. */
export type Body = Record<string, unknown> | unknown[] | string | Buffer | null

/** Intercepted response to return instead of the real server response. */
export interface MockResponse {
  /** HTTP status code (e.g. 200, 404, 500). */
  statusCode: number
  /** Response body. Objects and arrays are serialized to JSON. */
  body: Body
  /** Additional HTTP response headers. */
  headers: Record<string, string>
  /** MIME type for the Content-Type header. */
  contentType: string
  /**
   * Artificial delay in milliseconds before sending the response. Useful for
   * simulating slow APIs. 0 means no delay.
   */
  delayMs: number
}

/**
 * An incoming HTTP request, in engine-native types.
 *
 * The adapter builds this from mockttp's own request object so the engine
 * never depends on mockttp. Rules that only look at the URL work with the
 * defaults for every other field.
 */
export interface ProxyRequest {
  /** The full request URL. */
  url: string
  /** The HTTP method, uppercase. */
  method: string
  /** The request headers, lowercase keys. */
  headers: Record<string, string>
  /** The raw request body. Empty for requests without one. */
  body: Buffer
}

/** Build a {@link ProxyRequest}, filling in the defaults. */
export function proxyRequest(url: string, overrides: Partial<ProxyRequest> = {}): ProxyRequest {
  return {
    url,
    method: 'GET',
    headers: {},
    body: Buffer.alloc(0),
    ...overrides,
  }
}

/**
 * A rule as written in a JSON or YAML rules file.
 *
 * Field names are snake_case because a rules file is shared with the archived
 * Python implementation; {@link Rule} is the camelCase in-memory form, and
 * {@link Rule.fromData} converts between them.
 */
export interface RuleData {
  /** URL pattern. The only required field. */
  url_pattern: string
  /** Matching strategy name; defaults to `"glob"`. */
  matcher?: string
  /** Label for `check` output and verbose logs. */
  name?: string
  /** Status code to respond with; defaults to 200. */
  status_code?: number
  /**
   * Response body. Omitting the key entirely yields `{}`, while writing an
   * explicit `null` yields an empty body — the two are deliberately different.
   */
  body?: Body
  /** Extra response headers. */
  headers?: Record<string, string>
  /** Content-Type; defaults to `"application/json"`. */
  content_type?: string
  /** Artificial delay in milliseconds; defaults to 0. */
  delay_ms?: number
  /** Extra condition on a GraphQL request body. `null` or absent means none. */
  graphql?: GraphQLConditionData | null
}

/** A handler that builds the response body from the request. */
export type BodyHandler = (url: string, graphql: GraphQLRequest | null) => Body | Promise<Body>

/**
 * A single URL interception rule.
 *
 * Binds a URL pattern to a mock response. When the engine encounters a
 * request URL that matches `pattern`, it returns `response` instead of
 * forwarding the request to the real server.
 */
export class Rule {
  /** URL pattern string. Format depends on {@link matcher}. */
  readonly pattern: string
  /** The mock response to return when this rule matches. */
  readonly response: MockResponse
  /** Matching strategy — "glob" (fnmatch), "regex", or "exact". */
  readonly matcher: string
  /** Optional label for debugging and logging. */
  readonly name: string
  /**
   * Optional condition on the GraphQL request body. When set, the URL pattern
   * and the condition must both match, which is how several rules can share
   * one `/graphql` endpoint.
   */
  readonly graphql: GraphQLCondition | null
  /** Set by `RuleEngine.intercept` to compute the body per request. */
  bodyHandler?: BodyHandler

  /**
   * Build a rule directly. Every field of `response` that is left out falls
   * back to the default: 200, an empty JSON body, and no delay.
   *
   * Prefer {@link Rule.fromData} when the source is a rules file.
   */
  constructor(init: {
    pattern: string
    response?: Partial<MockResponse>
    matcher?: string
    name?: string
    graphql?: GraphQLCondition | null
  }) {
    this.pattern = init.pattern
    this.matcher = init.matcher ?? 'glob'
    this.name = init.name ?? ''
    this.graphql = init.graphql ?? null
    this.response = {
      statusCode: 200,
      body: null,
      headers: {},
      contentType: 'application/json',
      delayMs: 0,
      ...init.response,
    }
  }

  /**
   * Create a Rule from a rules-file entry.
   *
   * @throws If `url_pattern` is missing.
   */
  static fromData(data: RuleData): Rule {
    if (typeof data?.url_pattern !== 'string') {
      throw new Error(`rule is missing "url_pattern": ${JSON.stringify(data)}`)
    }
    return new Rule({
      pattern: data.url_pattern,
      matcher: data.matcher ?? 'glob',
      name: data.name ?? '',
      graphql: data.graphql != null ? GraphQLCondition.fromData(data.graphql) : null,
      response: {
        statusCode: data.status_code ?? 200,
        body: 'body' in data ? (data.body as Body) : {},
        headers: data.headers ?? {},
        contentType: data.content_type ?? 'application/json',
        delayMs: data.delay_ms ?? 0,
      },
    })
  }
}
