import { describe, expect, it } from 'vitest'

import { exactMatcher, getMatcher, globMatcher, MATCHERS, regexMatcher } from '../src/matching.js'

describe('globMatcher', () => {
  it('matches wildcards across path segments', () => {
    expect(globMatcher.match('https://example.com/api/users/123', '*/api/users/*')).toBe(true)
    expect(globMatcher.match('https://example.com/api/a/b/c', '*/api/*')).toBe(true)
  })

  it('needs a trailing wildcard to match a query string', () => {
    expect(globMatcher.match('https://e.com/api/rooms?no=42', '*/api/rooms')).toBe(false)
    expect(globMatcher.match('https://e.com/api/rooms?no=42', '*/api/rooms*')).toBe(true)
  })

  it('anchors the whole URL', () => {
    expect(globMatcher.match('https://example.com/api/users', '*/api/users/*')).toBe(false)
  })

  // Verified case by case against Python's fnmatch, so one rules file
  // behaves the same under either implementation.
  it.each([
    ['*.json', 'https://cdn.example.com/data.json', true],
    ['*/users/?', 'https://e.com/users/7', true],
    ['*/users/?', 'https://e.com/users/77', false],
    ['*/v[12]/*', 'https://e.com/v1/x', true],
    ['*/v[12]/*', 'https://e.com/v3/x', false],
    ['*/v[!12]/*', 'https://e.com/v3/x', true],
    ['*/v[!12]/*', 'https://e.com/v1/x', false],
    ['*[a-c]d*', 'https://e.com/bd', true],
    ['*[a-c]d*', 'https://e.com/zd', false],
    ['**/api/**', 'https://e.com/a/api/b', true],
    ['*a.b*', 'https://e.com/a.b/c', true],
    ['*a.b*', 'https://e.com/axb/c', false],
    ['*(x)*', 'https://e.com/(x)/y', true],
    ['*+z*', 'https://e.com/+z', true],
    ['*|y*', 'https://e.com/|y', true],
    ['*{a}*', 'https://e.com/{a}', true],
    ['*^c*', 'https://e.com/^c', true],
    ['*$d*', 'https://e.com/$d', true],
    ['*[*', 'https://e.com/[x', true],
    ['*]*', 'https://e.com/]x', true],
    ['*/한글/*', 'https://e.com/한글/x', true],
    ['', 'https://e.com', false],
    ['*', '', true],
  ])('fnmatch parity: %s vs %s', (pattern, url, expected) => {
    expect(globMatcher.match(url, pattern)).toBe(expected)
  })
})

describe('regexMatcher', () => {
  it('matches partially, like re.search', () => {
    expect(regexMatcher.match('https://api.example.com/users/42', String.raw`/users/\d+$`)).toBe(true)
    expect(regexMatcher.match('https://api.example.com/users/abc', String.raw`/users/\d+$`)).toBe(false)
  })

  it('caches compiled patterns', () => {
    const pattern = String.raw`api\.(dev|staging)\.example\.com`
    expect(regexMatcher.match('https://api.dev.example.com/x', pattern)).toBe(true)
    expect(regexMatcher.match('https://api.prod.example.com/x', pattern)).toBe(false)
  })
})

describe('exactMatcher', () => {
  it('compares the whole URL', () => {
    const url = 'https://example.com/api'
    expect(exactMatcher.match(url, url)).toBe(true)
    expect(exactMatcher.match(`${url}/`, url)).toBe(false)
  })
})

describe('getMatcher', () => {
  it('returns the registered matchers', () => {
    expect(getMatcher('glob')).toBe(MATCHERS['glob'])
    expect(getMatcher('regex')).toBe(MATCHERS['regex'])
    expect(getMatcher('exact')).toBe(MATCHERS['exact'])
  })

  it('rejects an unknown name', () => {
    expect(() => getMatcher('fuzzy')).toThrow(/Unknown matcher: 'fuzzy'/)
  })
})
