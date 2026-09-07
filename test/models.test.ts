import { describe, expect, it } from 'vitest'

import { proxyRequest, Rule } from '../src/models.js'

describe('Rule.fromData', () => {
  it('fills in the defaults', () => {
    const rule = Rule.fromData({ url_pattern: '*/api/*' })
    expect(rule.pattern).toBe('*/api/*')
    expect(rule.matcher).toBe('glob')
    expect(rule.name).toBe('')
    expect(rule.graphql).toBeNull()
    expect(rule.response).toEqual({
      statusCode: 200,
      body: {},
      headers: {},
      contentType: 'application/json',
      delayMs: 0,
    })
  })

  it('reads every documented key', () => {
    const rule = Rule.fromData({
      url_pattern: String.raw`/orders/\d+`,
      matcher: 'regex',
      name: 'orders',
      status_code: 201,
      body: { id: 1 },
      headers: { 'x-mock': 'yes' },
      content_type: 'text/plain',
      delay_ms: 250,
    })
    expect(rule.matcher).toBe('regex')
    expect(rule.name).toBe('orders')
    expect(rule.response.statusCode).toBe(201)
    expect(rule.response.body).toEqual({ id: 1 })
    expect(rule.response.headers).toEqual({ 'x-mock': 'yes' })
    expect(rule.response.contentType).toBe('text/plain')
    expect(rule.response.delayMs).toBe(250)
  })

  it('keeps an explicit null body distinct from a missing one', () => {
    expect(Rule.fromData({ url_pattern: '*', body: null }).response.body).toBeNull()
    expect(Rule.fromData({ url_pattern: '*' }).response.body).toEqual({})
  })

  it('builds a GraphQL condition when the block is present', () => {
    const rule = Rule.fromData({
      url_pattern: '*/graphql',
      graphql: { operation_name: 'GetUser', variables: { id: '1' } },
    })
    expect(rule.graphql?.operationName).toBe('GetUser')
    expect(rule.graphql?.variables).toEqual({ id: '1' })
  })

  it('rejects a rule without url_pattern', () => {
    // @ts-expect-error deliberately malformed, as a hand-edited rules file can be
    expect(() => Rule.fromData({ status_code: 200 })).toThrow(/missing "url_pattern"/)
  })
})

describe('proxyRequest', () => {
  it('defaults everything but the URL', () => {
    expect(proxyRequest('https://example.com')).toEqual({
      url: 'https://example.com',
      method: 'GET',
      headers: {},
      body: Buffer.alloc(0),
    })
  })

  it('takes overrides', () => {
    const request = proxyRequest('https://example.com', { method: 'POST', body: Buffer.from('x') })
    expect(request.method).toBe('POST')
    expect(request.body.toString()).toBe('x')
  })
})
