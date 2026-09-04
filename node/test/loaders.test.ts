import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RuleEngine } from '../src/engine.js'
import { getLoader, readRules, RulesFileLoader } from '../src/loaders.js'

let dir: string
let engine: RuleEngine

/** Write the file with a bumped mtime, so the loader sees a change. */
function write(file: string, contents: string, secondsAhead = 0): string {
  const target = path.join(dir, file)
  fs.writeFileSync(target, contents)
  if (secondsAhead) {
    const when = new Date(Date.now() + secondsAhead * 1000)
    fs.utimesSync(target, when, when)
  }
  return target
}

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pproxy-'))
  engine = new RuleEngine()
  vi.spyOn(console, 'log').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
  fs.rmSync(dir, { recursive: true, force: true })
})

describe('RulesFileLoader (JSON)', () => {
  it('loads rules on the first call', () => {
    const file = write('rules.json', JSON.stringify([{ url_pattern: '*/api/*' }]))
    expect(new RulesFileLoader(file, engine).reloadIfChanged()).toBe(true)
    expect(engine.rules).toHaveLength(1)
  })

  it('skips reloading an unchanged file', () => {
    const file = write('rules.json', JSON.stringify([{ url_pattern: '*/api/*' }]))
    const loader = new RulesFileLoader(file, engine)
    expect(loader.reloadIfChanged()).toBe(true)
    expect(loader.reloadIfChanged()).toBe(false)
  })

  it('picks up an edit', () => {
    const file = write('rules.json', JSON.stringify([{ url_pattern: '*/old/*' }]))
    const loader = new RulesFileLoader(file, engine)
    loader.reloadIfChanged()

    write('rules.json', JSON.stringify([{ url_pattern: '*/new/*' }]), 2)
    expect(loader.reloadIfChanged()).toBe(true)
    expect(engine.rules[0]?.pattern).toBe('*/new/*')
  })

  it('keeps the last valid rules when an edit does not parse', () => {
    const file = write('rules.json', JSON.stringify([{ url_pattern: '*/api/*' }]))
    const log = vi.fn()
    const loader = new RulesFileLoader(file, engine, log)
    loader.reloadIfChanged()

    write('rules.json', '[{"url_pattern": ', 2)
    expect(loader.reloadIfChanged()).toBe(false)
    expect(engine.rules[0]?.pattern).toBe('*/api/*')
    expect(log.mock.calls[0]?.[0]).toMatch(/JSON parse error \(keeping last valid rules\)/)
  })

  it('keeps the last valid rules when a rule is malformed', () => {
    const file = write('rules.json', JSON.stringify([{ url_pattern: '*/api/*' }]))
    const log = vi.fn()
    const loader = new RulesFileLoader(file, engine, log)
    loader.reloadIfChanged()

    write('rules.json', JSON.stringify([{ status_code: 200 }]), 2)
    expect(loader.reloadIfChanged()).toBe(false)
    expect(engine.rules[0]?.pattern).toBe('*/api/*')
  })

  it('reports a missing file without throwing', () => {
    const log = vi.fn()
    const loader = new RulesFileLoader(path.join(dir, 'nope.json'), engine, log)
    expect(loader.reloadIfChanged()).toBe(false)
    expect(log.mock.calls[0]?.[0]).toMatch(/not found/)
  })

  it('retries once the file appears', () => {
    const file = path.join(dir, 'later.json')
    const loader = new RulesFileLoader(file, engine, vi.fn())
    expect(loader.reloadIfChanged()).toBe(false)
    write('later.json', JSON.stringify([{ url_pattern: '*' }]))
    expect(loader.reloadIfChanged()).toBe(true)
  })
})

describe('RulesFileLoader (YAML)', () => {
  it('loads the YAML form of a rules file', () => {
    const file = write(
      'rules.yaml',
      ["- url_pattern: '*/api/users/*'", '  status_code: 200', '  body:', '    users: []'].join('\n'),
    )
    expect(new RulesFileLoader(file, engine).reloadIfChanged()).toBe(true)
    expect(engine.rules[0]?.pattern).toBe('*/api/users/*')
    expect(engine.rules[0]?.response.body).toEqual({ users: [] })
  })

  it('keeps the last valid rules when the YAML does not parse', () => {
    const file = write('rules.yaml', "- url_pattern: '*'")
    const log = vi.fn()
    const loader = new RulesFileLoader(file, engine, log)
    loader.reloadIfChanged()

    write('rules.yaml', '- [unclosed', 2)
    expect(loader.reloadIfChanged()).toBe(false)
    expect(log.mock.calls[0]?.[0]).toMatch(/YAML parse error/)
  })

  it('treats an empty file as a parse error rather than crashing', () => {
    const file = write('rules.yaml', '')
    const log = vi.fn()
    expect(new RulesFileLoader(file, engine, log).reloadIfChanged()).toBe(false)
    expect(log.mock.calls[0]?.[0]).toMatch(/must be a list/)
  })
})

describe('getLoader', () => {
  it.each([
    ['rules.json', 'JSON'],
    ['rules.yaml', 'YAML'],
    ['rules.yml', 'YAML'],
    ['RULES.JSON', 'JSON'],
  ])('picks the format for %s', (file, format) => {
    const loader = getLoader(path.join(dir, file), engine) as RulesFileLoader
    expect(loader.format.name).toBe(format)
  })

  it('rejects an unsupported extension', () => {
    expect(() => getLoader('rules.toml', engine)).toThrow(/Unsupported rules file/)
  })
})

describe('readRules', () => {
  it('returns the parsed rules', () => {
    const file = write('rules.json', JSON.stringify([{ url_pattern: '*' }]))
    expect(readRules(file)).toEqual([{ url_pattern: '*' }])
  })

  it('throws instead of swallowing a parse error, unlike the loader', () => {
    const file = write('rules.json', '[{')
    expect(() => readRules(file)).toThrow()
  })
})
