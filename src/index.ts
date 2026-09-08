/**
 * pproxy — URL pattern-based HTTP response interception.
 *
 * The rule engine is independent of the proxy: import {@link RuleEngine} on
 * its own to unit test rules, or {@link startProxy} to run them against real
 * traffic. Nothing in the engine layer touches mockttp, so a rule can be
 * asserted on in a plain unit test with no server and no certificates.
 *
 * Rules can come from a file — the shape `pproxy run rules.json` loads — or be
 * registered in code, where a handler computes the body per request.
 *
 * @example Assert on a rule with no proxy running
 * ```ts
 * import { RuleEngine } from 'pproxy'
 *
 * const engine = new RuleEngine().load([
 *   { url_pattern: 'https://example.com/api/*', status_code: 200, body: { users: [] } },
 * ])
 *
 * const mock = await engine.match('https://example.com/api/users/1')
 * mock?.statusCode // 200
 * ```
 *
 * @example Intercept live traffic
 * ```ts
 * import { RuleEngine, startProxy } from 'pproxy'
 *
 * const engine = new RuleEngine().load([{ url_pattern: 'https://example.com/api/*', body: {} }])
 * const server = await startProxy(engine, null, { port: 8080 })
 *
 * await server.stop()
 * ```
 *
 * @module
 */

export { RuleEngine, serializeBody } from './engine.js'
export type { InterceptHook, InterceptOptions, Match } from './engine.js'
export { Rule, proxyRequest } from './models.js'
export type { Body, BodyHandler, MockResponse, ProxyRequest, RuleData } from './models.js'
export {
  GraphQLCondition,
  parseGraphql,
  extractOperationName,
  containsSubset,
} from './graphql.js'
export type { GraphQLConditionData, GraphQLRequest } from './graphql.js'
export {
  MATCHERS,
  getMatcher,
  translateGlob,
  globMatcher,
  regexMatcher,
  exactMatcher,
} from './matching.js'
export type { Matcher, MatcherName } from './matching.js'
export { RulesFileLoader, FORMATS, getFormat, getLoader, readRules } from './loaders.js'
export type { Loader, RuleFormat } from './loaders.js'
export { startProxy, CORS_OPTIONS } from './proxy.js'
export type { ProxyOptions } from './proxy.js'
export { runtimeDir, caPaths, ensureCA, trustCA, trustCommand } from './ca.js'
export type { CAPaths } from './ca.js'
