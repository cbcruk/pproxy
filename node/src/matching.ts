/**
 * URL matching strategies.
 *
 * Ported from `src/pproxy/matching.py`. The `glob` matcher reproduces
 * Python's `fnmatch` semantics so a rules file behaves identically under
 * either implementation.
 */

export type MatcherName = 'glob' | 'regex' | 'exact'

export interface Matcher {
  /** Test whether a URL matches the given pattern. */
  match(url: string, pattern: string): boolean
}

const STAR = Symbol('star')
type Token = string | typeof STAR

/** Escape a single literal character for use inside a regular expression. */
function escapeChar(char: string): string {
  return /[\\^$.*+?()[\]{}|/]/.test(char) ? `\\${char}` : char
}

/**
 * Translate an fnmatch pattern to a regular expression source string.
 *
 * Mirrors `fnmatch.translate`: `*` matches any run of characters
 * (newlines included, hence the `s` flag on the compiled expression),
 * `?` matches exactly one, and `[seq]` / `[!seq]` are character classes.
 * Python's normalization of degenerate ranges (`--`, `&&`, `||`) is not
 * reproduced — those are invalid in URLs in practice.
 */
export function translateGlob(pattern: string): string {
  const tokens: Token[] = []
  let i = 0
  const n = pattern.length

  while (i < n) {
    const char = pattern[i]!
    i += 1

    if (char === '*') {
      // Collapse runs of `*` so `**` costs no more than `*`.
      if (tokens[tokens.length - 1] !== STAR) tokens.push(STAR)
    } else if (char === '?') {
      tokens.push('.')
    } else if (char === '[') {
      let j = i
      if (j < n && pattern[j] === '!') j += 1
      if (j < n && pattern[j] === ']') j += 1
      while (j < n && pattern[j] !== ']') j += 1

      if (j >= n) {
        // Unterminated class — treat the bracket as a literal.
        tokens.push('\\[')
      } else {
        let stuff = pattern.slice(i, j).replace(/\\/g, '\\\\')
        i = j + 1
        if (!stuff) {
          tokens.push('(?!)') // empty class: never matches
        } else if (stuff === '!') {
          tokens.push('.') // negated empty class: matches anything
        } else {
          if (stuff.startsWith('!')) stuff = `^${stuff.slice(1)}`
          else if (stuff.startsWith('^') || stuff.startsWith('[')) stuff = `\\${stuff}`
          tokens.push(`[${stuff}]`)
        }
      }
    } else {
      tokens.push(escapeChar(char))
    }
  }

  const body = tokens.map((token) => (token === STAR ? '.*' : token)).join('')
  return `^${body}$`
}

const globCache = new Map<string, RegExp>()
const regexCache = new Map<string, RegExp>()

function cached(cache: Map<string, RegExp>, key: string, build: () => RegExp): RegExp {
  let compiled = cache.get(key)
  if (!compiled) {
    compiled = build()
    cache.set(key, compiled)
  }
  return compiled
}

/**
 * Matches URLs using shell-style wildcards.
 *
 * `*​/api/users/*` matches `https://example.com/api/users/123`.
 */
export const globMatcher: Matcher = {
  match(url, pattern) {
    return cached(globCache, pattern, () => new RegExp(translateGlob(pattern), 's')).test(url)
  },
}

/**
 * Matches URLs using regular expressions.
 *
 * Partial matches count, as with Python's `re.search`, so `/users/\d+$`
 * matches any URL ending in `/users/42`.
 */
export const regexMatcher: Matcher = {
  match(url, pattern) {
    return cached(regexCache, pattern, () => new RegExp(pattern, 's')).test(url)
  },
}

/** Matches URLs by exact string equality. */
export const exactMatcher: Matcher = {
  match(url, pattern) {
    return url === pattern
  },
}

/** Registry of available matchers. Add new matchers here. */
export const MATCHERS: Record<string, Matcher> = {
  glob: globMatcher,
  regex: regexMatcher,
  exact: exactMatcher,
}

/**
 * Look up a matcher by name.
 *
 * @throws If the name is not registered in {@link MATCHERS}.
 */
export function getMatcher(name: string): Matcher {
  const matcher = MATCHERS[name]
  if (!matcher) {
    throw new Error(`Unknown matcher: '${name}'. Choose from ${Object.keys(MATCHERS).join(', ')}`)
  }
  return matcher
}
