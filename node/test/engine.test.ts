import { describe, expect, it, vi } from 'vitest'

import { RuleEngine, serializeBody } from '../src/engine.js'
import { proxyRequest, Rule } from '../src/models.js'
import type { GraphQLRequest } from '../src/graphql.js'

const gqlRequest = (payload: unknown) =>
  proxyRequest('https://example.com/graphql', {
    method: 'POST',
    body: Buffer.from(JSON.stringify(payload)),
  })

describe('rule registration', () => {
  it('adds a rule', async () => {
    const engine = new RuleEngine().addRule(new Rule({ pattern: '*/api/*' }))
    expect(await engine.match('https://example.com/api/users')).not.toBeNull()
  })

  it('loads from rules-file data', async () => {
    const engine = new RuleEngine().load([{ url_pattern: '*/api/*', body: { ok: true } }])
    expect(await engine.match('https://example.com/api/users')).not.toBeNull()
  })

  it('replaces existing rules on load', async () => {
    const engine = new RuleEngine().addRule(new Rule({ pattern: '*/old/*' }))
    engine.load([{ url_pattern: '*/new/*' }])
    expect(await engine.match('https://example.com/old/path')).toBeNull()
    expect(await engine.match('https://example.com/new/path')).not.toBeNull()
  })

  it('rejects a rules file that is not a list', () => {
    // @ts-expect-error a YAML file of `{}` parses to an object, not a list
    expect(() => new RuleEngine().load({ url_pattern: '*' })).toThrow(/must be a list/)
  })

  it('chains', () => {
    const engine = new RuleEngine()
    expect(engine.addRule(new Rule({ pattern: '*' }))).toBe(engine)
  })
})

describe('matching', () => {
  it('returns the mock response on a glob match', async () => {
    const engine = new RuleEngine().load([
      { url_pattern: '*/api/*', status_code: 200, body: { ok: true } },
    ])
    const result = await engine.match('https://example.com/api/users')
    expect(result?.statusCode).toBe(200)
    expect(result?.body).toEqual({ ok: true })
  })

  it('returns null when nothing matches', async () => {
    const engine = new RuleEngine().load([{ url_pattern: '*/api/*' }])
    expect(await engine.match('https://example.com/health')).toBeNull()
  })

  it('supports the regex matcher', async () => {
    const engine = new RuleEngine().addRule(
      new Rule({ pattern: String.raw`/users/\d+$`, matcher: 'regex' }),
    )
    expect(await engine.match('https://api.example.com/users/42')).not.toBeNull()
    expect(await engine.match('https://api.example.com/users/abc')).toBeNull()
  })

  it('supports the exact matcher', async () => {
    const url = 'https://example.com/api/health'
    const engine = new RuleEngine().addRule(new Rule({ pattern: url, matcher: 'exact' }))
    expect(await engine.match(url)).not.toBeNull()
    expect(await engine.match(`${url}/`)).toBeNull()
  })

  it('lets the first matching rule win', async () => {
    const engine = new RuleEngine().load([
      { url_pattern: '*/api/*', body: { first: true } },
      { url_pattern: '*/api/users/*', body: { second: true } },
    ])
    expect((await engine.match('https://example.com/api/users/1'))?.body).toEqual({ first: true })
  })

  it('returns null with no rules at all', async () => {
    expect(await new RuleEngine().match('https://example.com/anything')).toBeNull()
  })

  it('rejects an unknown matcher when the rule is reached', async () => {
    const engine = new RuleEngine().load([{ url_pattern: '*', matcher: 'fuzzy' }])
    await expect(engine.match('https://example.com')).rejects.toThrow(/Unknown matcher/)
  })
})

describe('intercept handlers', () => {
  it('builds the body from the URL', async () => {
    const engine = new RuleEngine().intercept('*/search*', (url) => ({
      query: url.split('q=').at(-1),
    }))
    expect((await engine.match('https://api.example.com/search?q=hello'))?.body).toEqual({
      query: 'hello',
    })
  })

  it('names the rule after the handler', () => {
    const engine = new RuleEngine().intercept('*/api/*', function myHandler() {
      return {}
    })
    expect(engine.rules[0]?.name).toBe('myHandler')
  })

  it('takes response options', async () => {
    const engine = new RuleEngine().intercept('*/api/*', () => 'created', {
      statusCode: 201,
      contentType: 'text/plain',
    })
    const result = await engine.match('https://example.com/api/resource')
    expect(result?.statusCode).toBe(201)
    expect(result?.contentType).toBe('text/plain')
    expect(result?.body).toBe('created')
  })

  it('awaits an async handler', async () => {
    const engine = new RuleEngine().intercept('*/api/*', async () => ({ async: true }))
    expect((await engine.match('https://example.com/api/x'))?.body).toEqual({ async: true })
  })
})

describe('hooks', () => {
  it('fires on a match', async () => {
    const hook = vi.fn()
    const engine = new RuleEngine().load([{ url_pattern: '*/api/*' }])
    engine.addHook(hook)
    await engine.match('https://example.com/api/users')
    expect(hook).toHaveBeenCalledOnce()
    expect(hook.mock.calls[0]?.[0]).toBe('https://example.com/api/users')
    expect(hook.mock.calls[0]?.[1].pattern).toBe('*/api/*')
  })

  it('does not fire without a match', async () => {
    const hook = vi.fn()
    const engine = new RuleEngine().load([{ url_pattern: '*/api/*' }])
    engine.addHook(hook)
    await engine.match('https://example.com/health')
    expect(hook).not.toHaveBeenCalled()
  })

  it('does not fire from findRule', () => {
    const hook = vi.fn()
    const engine = new RuleEngine().load([{ url_pattern: '*' }])
    engine.addHook(hook)
    expect(engine.findRule('https://example.com')).not.toBeNull()
    expect(hook).not.toHaveBeenCalled()
  })

  it('fires every registered hook', async () => {
    const [a, b] = [vi.fn(), vi.fn()]
    const engine = new RuleEngine().load([{ url_pattern: '*' }])
    engine.addHook(a)
    engine.addHook(b)
    await engine.match('https://example.com')
    expect(a).toHaveBeenCalledOnce()
    expect(b).toHaveBeenCalledOnce()
  })
})

describe('serializeBody', () => {
  it.each([
    ['an object', { key: 'value' }, '{"key":"value"}'],
    ['an array', [1, 2, 3], '[1,2,3]'],
    ['a string', 'hello', 'hello'],
    ['null', null, ''],
    ['non-ASCII text', { name: '홍길동' }, '{"name":"홍길동"}'],
  ])('serializes %s', (_label, body, expected) => {
    expect(serializeBody(body as never).toString('utf8')).toBe(expected)
  })

  it('passes buffers through untouched', () => {
    const raw = Buffer.from([0x00, 0xff])
    expect(serializeBody(raw)).toBe(raw)
  })
})

describe('GraphQL matching', () => {
  const engine = () =>
    new RuleEngine().load([
      {
        name: 'user',
        url_pattern: '*/graphql',
        graphql: { operation_name: 'GetUser' },
        body: { data: { user: { id: '1' } } },
      },
      {
        name: 'posts',
        url_pattern: '*/graphql',
        graphql: { operation_name: 'GetPosts' },
        body: { data: { posts: [] } },
      },
    ])

  it('picks the rule for the operation', async () => {
    const result = await engine().match(
      gqlRequest({ operationName: 'GetPosts', query: 'query GetPosts { posts { id } }' }),
    )
    expect(result?.body).toEqual({ data: { posts: [] } })
  })

  it('passes an unknown operation through', async () => {
    expect(
      await engine().match(
        gqlRequest({ operationName: 'GetComments', query: 'query GetComments { comments { id } }' }),
      ),
    ).toBeNull()
  })

  it('passes a non-GraphQL body through', async () => {
    const request = proxyRequest('https://example.com/graphql', {
      method: 'POST',
      body: Buffer.from('not json'),
    })
    expect(await engine().match(request)).toBeNull()
  })

  it('passes a bodyless request through', async () => {
    expect(await engine().match('https://example.com/graphql')).toBeNull()
  })

  it('narrows on variables, first match winning', async () => {
    const narrowed = new RuleEngine().load([
      {
        url_pattern: '*/graphql',
        graphql: { operation_name: 'GetUser', variables: { id: '42' } },
        body: { data: { user: { id: '42' } } },
      },
      {
        url_pattern: '*/graphql',
        graphql: { operation_name: 'GetUser' },
        status_code: 404,
        body: { errors: [{ message: 'not found' }] },
      },
    ])
    const query = 'query GetUser($id: ID!) { user(id: $id) { id } }'

    expect((await narrowed.match(gqlRequest({ query, variables: { id: '42' } })))?.body).toEqual({
      data: { user: { id: '42' } },
    })
    expect((await narrowed.match(gqlRequest({ query, variables: { id: '7' } })))?.statusCode).toBe(404)
  })

  it('still respects rule order against an unconditional rule', async () => {
    const ordered = new RuleEngine().load([
      { url_pattern: '*/graphql', body: { data: null } },
      {
        url_pattern: '*/graphql',
        graphql: { operation_name: 'GetUser' },
        body: { data: { user: { id: '1' } } },
      },
    ])
    const result = await ordered.match(gqlRequest({ query: 'query GetUser { user { id } }' }))
    expect(result?.body).toEqual({ data: null })
  })

  it('gives hooks the URL and the matched rule', async () => {
    const hook = vi.fn()
    const e = engine()
    e.addHook(hook)
    await e.match(gqlRequest({ query: 'query GetUser { user { id } }' }))
    expect(hook.mock.calls[0]?.[1].name).toBe('user')
  })

  it('hands the parsed request to an intercept handler', async () => {
    const engineWithHandler = new RuleEngine().intercept(
      '*/graphql',
      (_url, gql: GraphQLRequest | null) => ({ data: { user: { id: gql?.variables['id'] } } }),
      { graphql: { operation_name: 'GetUser' } },
    )
    const result = await engineWithHandler.match(
      gqlRequest({
        query: 'query GetUser($id: ID!) { user(id: $id) { id } }',
        variables: { id: '99' },
      }),
    )
    expect(result?.body).toEqual({ data: { user: { id: '99' } } })
  })

  it('parses the body once even with several GraphQL rules', async () => {
    const request = gqlRequest({ query: 'query GetPosts { posts { id } }' })
    const spy = vi.spyOn(JSON, 'parse')
    await engine().match(request)
    expect(spy).toHaveBeenCalledTimes(1)
    spy.mockRestore()
  })
})
