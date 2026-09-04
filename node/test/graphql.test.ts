import { describe, expect, it } from 'vitest'

import {
  containsSubset,
  extractOperationName,
  GraphQLCondition,
  parseGraphql,
} from '../src/graphql.js'

const body = (payload: unknown) => Buffer.from(JSON.stringify(payload))

describe('parseGraphql', () => {
  it('reads query, operation name, and variables', () => {
    const parsed = parseGraphql(
      body({ query: 'query GetUser { user { id } }', operationName: 'GetUser', variables: { id: '1' } }),
    )
    expect(parsed).toEqual({
      query: 'query GetUser { user { id } }',
      operationName: 'GetUser',
      variables: { id: '1' },
    })
  })

  it('recovers the operation name from the query text', () => {
    expect(parseGraphql(body({ query: 'mutation UpdateUser { ok }' }))?.operationName).toBe('UpdateUser')
  })

  it('leaves anonymous operations unnamed', () => {
    expect(parseGraphql(body({ query: '{ viewer { id } }' }))?.operationName).toBe('')
  })

  it('defaults missing or malformed variables to an empty map', () => {
    expect(parseGraphql(body({ query: 'query A { a }' }))?.variables).toEqual({})
    expect(parseGraphql(body({ query: 'query A { a }', variables: 'nope' }))?.variables).toEqual({})
  })

  it.each([
    ['an empty body', Buffer.alloc(0)],
    ['non-JSON', Buffer.from('not json')],
    ['a batched array', body([{ query: 'query A { a }' }])],
    ['a payload without a query', body({ operationName: 'GetUser' })],
    ['a persisted query hash only', body({ extensions: { persistedQuery: { sha256Hash: 'abc' } } })],
    ['a blank query', body({ query: '   ' })],
  ])('passes through %s', (_label, input) => {
    expect(parseGraphql(input)).toBeNull()
  })
})

describe('extractOperationName', () => {
  it.each([
    ['query GetUser { user { id } }', 'GetUser'],
    ['mutation  CreatePost ($x: Int) { ok }', 'CreatePost'],
    ['subscription OnTick { tick }', 'OnTick'],
    ['{ viewer { id } }', ''],
  ])('%s', (query, expected) => {
    expect(extractOperationName(query)).toBe(expected)
  })
})

describe('containsSubset', () => {
  it('ignores extra keys in the request', () => {
    expect(containsSubset({ id: '1', page: 2 }, { id: '1' })).toBe(true)
  })

  it('compares nested objects the same way', () => {
    expect(containsSubset({ filter: { status: 'open', tag: 'x' } }, { filter: { status: 'open' } })).toBe(true)
    expect(containsSubset({ filter: { status: 'closed' } }, { filter: { status: 'open' } })).toBe(false)
  })

  it('requires arrays to match in full', () => {
    expect(containsSubset({ ids: [1, 2] }, { ids: [1, 2] })).toBe(true)
    expect(containsSubset({ ids: [1, 2, 3] }, { ids: [1, 2] })).toBe(false)
  })

  it('fails when a key is missing or the shape differs', () => {
    expect(containsSubset({}, { id: '1' })).toBe(false)
    expect(containsSubset('scalar', { id: '1' })).toBe(false)
  })
})

describe('GraphQLCondition', () => {
  const request = { query: 'query GetUser { user { id } }', operationName: 'GetUser', variables: { id: '42' } }

  it('matches any operation when empty', () => {
    expect(GraphQLCondition.fromData({}).matches(request)).toBe(true)
  })

  it('matches on the operation name', () => {
    expect(GraphQLCondition.fromData({ operation_name: 'GetUser' }).matches(request)).toBe(true)
    expect(GraphQLCondition.fromData({ operation_name: 'GetPosts' }).matches(request)).toBe(false)
  })

  it('narrows on variables as a subset', () => {
    expect(GraphQLCondition.fromData({ variables: { id: '42' } }).matches(request)).toBe(true)
    expect(GraphQLCondition.fromData({ variables: { id: '7' } }).matches(request)).toBe(false)
  })

  it('treats null variables as empty', () => {
    expect(GraphQLCondition.fromData({ variables: null }).variables).toEqual({})
  })

  it('describes itself for CLI output with sorted keys', () => {
    expect(GraphQLCondition.fromData({ operation_name: 'GetUser' }).describe()).toBe('GetUser')
    expect(GraphQLCondition.fromData({}).describe()).toBe('*')
    expect(
      GraphQLCondition.fromData({ operation_name: 'GetUser', variables: { page: 2, id: '42' } }).describe(),
    ).toBe('GetUser {"id": "42", "page": 2}')
  })
})
