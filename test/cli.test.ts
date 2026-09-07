import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { checkCommand, main, parseArgs } from '../src/cli.js'

let dir: string
let out: string[]
let err: string[]

function rules(name: string, contents: unknown): string {
  const file = path.join(dir, name)
  fs.writeFileSync(file, typeof contents === 'string' ? contents : JSON.stringify(contents))
  return file
}

const check = (file: string) =>
  checkCommand({ host: '127.0.0.1', port: 8080, verbose: false, httpOnly: false, positional: [file] })

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pproxy-cli-'))
  out = []
  err = []
  vi.spyOn(console, 'log').mockImplementation((...args) => void out.push(args.join(' ')))
  vi.spyOn(console, 'error').mockImplementation((...args) => void err.push(args.join(' ')))
})

afterEach(() => {
  vi.restoreAllMocks()
  fs.rmSync(dir, { recursive: true, force: true })
})

describe('parseArgs', () => {
  it('defaults to loopback on 8080', () => {
    const options = parseArgs(['rules.json'])
    expect(options).toMatchObject({
      host: '127.0.0.1',
      port: 8080,
      verbose: false,
      httpOnly: false,
      positional: ['rules.json'],
    })
  })

  it('reads the long and short forms', () => {
    expect(parseArgs(['rules.json', '--host', '0.0.0.0', '--port', '9090', '--verbose'])).toMatchObject({
      host: '0.0.0.0',
      port: 9090,
      verbose: true,
    })
    expect(parseArgs(['-H', '0.0.0.0', '-p', '9090', '-v'])).toMatchObject({
      host: '0.0.0.0',
      port: 9090,
      verbose: true,
    })
  })

  it('rejects a bad port', () => {
    expect(() => parseArgs(['-p', 'http'])).toThrow(/invalid port/)
    expect(() => parseArgs(['-p', '70000'])).toThrow(/invalid port/)
  })

  it('rejects a flag with no value', () => {
    expect(() => parseArgs(['--port'])).toThrow(/expected a value/)
  })

  it('rejects an unknown flag', () => {
    expect(() => parseArgs(['--fast'])).toThrow(/unrecognized argument: --fast/)
  })
})

describe('check', () => {
  it('lists the rules and their targets', () => {
    const file = rules('rules.json', [
      { url_pattern: '*/api/users/*', status_code: 200, name: 'users' },
      { url_pattern: String.raw`/orders/\d+`, matcher: 'regex', status_code: 201 },
    ])
    expect(check(file)).toBe(0)
    expect(out).toEqual([
      '  glob  */api/users/* → 200 (users)',
      String.raw`  regex /orders/\d+ → 201`,
      '2 rules OK',
    ])
  })

  it('shows the GraphQL condition', () => {
    const file = rules('rules.json', [
      {
        url_pattern: '*/graphql',
        graphql: { operation_name: 'GetUser', variables: { id: '42' } },
        name: 'user',
      },
    ])
    expect(check(file)).toBe(0)
    expect(out[0]).toBe('  glob  */graphql graphql:GetUser {"id": "42"} → 200 (user)')
  })

  it('fails on a missing file', () => {
    expect(check(path.join(dir, 'nope.json'))).toBe(1)
    expect(err[0]).toMatch(/not found/)
  })

  it('fails on a parse error', () => {
    expect(check(rules('rules.json', '[{'))).toBe(1)
    expect(err[0]).toMatch(/failed to load/)
  })

  it('fails on a rule without url_pattern', () => {
    expect(check(rules('rules.json', [{ status_code: 200 }]))).toBe(1)
    expect(err[0]).toMatch(/missing "url_pattern"/)
  })

  it('fails on an unknown matcher', () => {
    expect(check(rules('rules.json', [{ url_pattern: '*', matcher: 'fuzzy' }]))).toBe(1)
    expect(err[0]).toMatch(/Unknown matcher/)
  })

  it('fails on an empty rules file', () => {
    expect(check(rules('rules.json', []))).toBe(1)
    expect(err[0]).toMatch(/no rules loaded/)
  })

  it('fails on an unsupported extension', () => {
    expect(check(rules('rules.toml', 'x = 1'))).toBe(1)
    expect(err[0]).toMatch(/Unsupported rules file/)
  })
})

describe('main', () => {
  it('prints usage without a command', async () => {
    expect(await main([])).toBe(2)
    expect(out.join('\n')).toMatch(/usage: pproxy/)
  })

  it('prints usage for --help', async () => {
    expect(await main(['--help'])).toBe(0)
  })

  it('rejects an unknown command', async () => {
    expect(await main(['serve'])).toBe(2)
    expect(err.join('\n')).toMatch(/unknown command: serve/)
  })

  it('rejects run without a rules file', async () => {
    expect(await main(['run'])).toBe(2)
    expect(err.join('\n')).toMatch(/missing rules file/)
  })

  it('rejects an unknown cert action', async () => {
    expect(await main(['cert', 'renew'])).toBe(2)
    expect(err.join('\n')).toMatch(/unknown action 'renew'/)
  })
})
