/**
 * GraphQL request parsing and rule conditions.
 *
 * Ported from `archive/python/src/pproxy/graphql.py`.
 */

/**
 * Extracts the operation name from raw query text.
 *
 * Used only when the request omits the `operationName` field, which many
 * GraphQL clients do for single-operation documents.
 */
const OPERATION_NAME_RE = /\b(?:query|mutation|subscription)\s+([_A-Za-z][_0-9A-Za-z]*)/

/** A parsed GraphQL request payload. */
export interface GraphQLRequest {
  /** The raw GraphQL document text. */
  query: string
  /**
   * The operation name sent by the client, or the one recovered from
   * `query`. Empty for anonymous operations.
   */
  operationName: string
  /** The variables map sent with the operation. */
  variables: Record<string, unknown>
}

/** The `graphql` block of a rule, as it appears in a rules file. */
export interface GraphQLConditionData {
  operation_name?: string
  variables?: Record<string, unknown> | null
}

/**
 * An extra condition on a rule, evaluated against the request body.
 *
 * All non-empty fields must match (AND). An empty condition matches any
 * parseable GraphQL request, which is a way to mock a whole endpoint.
 */
export class GraphQLCondition {
  constructor(
    /** Required operation name. Empty means "any operation". */
    readonly operationName: string = '',
    /**
     * Variables that must be present in the request. Compared as a subset —
     * extra variables in the request are ignored, and nested objects are
     * compared the same way.
     */
    readonly variables: Record<string, unknown> = {},
  ) {}

  /** Create a condition from the `graphql` block of a rule. */
  static fromData(data: GraphQLConditionData): GraphQLCondition {
    return new GraphQLCondition(data.operation_name ?? '', data.variables ?? {})
  }

  /** Test whether a parsed GraphQL request satisfies this condition. */
  matches(request: GraphQLRequest): boolean {
    if (this.operationName && this.operationName !== request.operationName) return false
    return containsSubset(request.variables, this.variables)
  }

  /** Render the condition as a one-line label for CLI output. */
  describe(): string {
    const parts = [this.operationName || '*']
    if (Object.keys(this.variables).length > 0) parts.push(stableStringify(this.variables))
    return parts.join(' ')
  }
}

/**
 * Parse a GraphQL request body.
 *
 * Handles the `application/json` POST form — a single object with `query`,
 * and optionally `operationName` and `variables`. Batched (array) payloads,
 * `GET` query strings, `application/graphql` bodies, and persisted queries
 * without query text are not recognized and yield `null`, so the request
 * falls through to the real server.
 */
export function parseGraphql(body: string | Buffer | null | undefined): GraphQLRequest | null {
  if (!body || body.length === 0) return null

  let payload: unknown
  try {
    payload = JSON.parse(typeof body === 'string' ? body : body.toString('utf8'))
  } catch {
    return null
  }
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) return null

  const record = payload as Record<string, unknown>

  const query = record['query']
  if (typeof query !== 'string' || !query.trim()) return null

  const rawVariables = record['variables']
  const variables =
    typeof rawVariables === 'object' && rawVariables !== null && !Array.isArray(rawVariables)
      ? (rawVariables as Record<string, unknown>)
      : {}

  const sentName = record['operationName']
  const operationName =
    typeof sentName === 'string' && sentName ? sentName : extractOperationName(query)

  return { query, operationName, variables }
}

/**
 * Recover the operation name from raw GraphQL document text.
 *
 * @returns The first operation name found, or `''` for an anonymous operation.
 */
export function extractOperationName(query: string): string {
  return OPERATION_NAME_RE.exec(query)?.[1] ?? ''
}

/**
 * Test whether `expected` is contained in `actual`.
 *
 * Objects are compared key by key, recursively; keys absent from `expected`
 * are ignored. Everything else is compared by deep equality, so arrays must
 * match in full.
 */
export function containsSubset(actual: unknown, expected: unknown): boolean {
  if (isPlainObject(expected)) {
    if (!isPlainObject(actual)) return false
    return Object.entries(expected).every(
      ([key, value]) => key in actual && containsSubset(actual[key], value),
    )
  }
  return deepEqual(actual, expected)
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false
    return a.every((item, index) => deepEqual(item, b[index]))
  }
  if (isPlainObject(a) && isPlainObject(b)) {
    const aKeys = Object.keys(a)
    if (aKeys.length !== Object.keys(b).length) return false
    return aKeys.every((key) => key in b && deepEqual(a[key], b[key]))
  }
  return false
}

/**
 * Serialize a value with sorted keys, matching `json.dumps(..., sort_keys=True)`
 * down to the separators, so both implementations print the same `check` output.
 */
export function stableStringify(value: unknown): string {
  if (value === null || value === undefined) return 'null'
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(', ')}]`
  if (isPlainObject(value)) {
    const entries = Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}: ${stableStringify(value[key])}`)
    return `{${entries.join(', ')}}`
  }
  return JSON.stringify(value) ?? 'null'
}
