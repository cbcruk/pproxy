/**
 * Rules file reading and hot-reload.
 *
 * Ported from `archive/python/src/pproxy/loaders/`. The loader watches a file's mtime and
 * re-reads it into the engine when it changes; if the new content fails to
 * parse, the last valid rules are kept so a half-typed edit never takes the
 * proxy down. `readRules` is the same read without that safety net, for
 * `pproxy check`, which exists to report exactly what is wrong.
 */

import * as fs from 'node:fs'
import * as path from 'node:path'
import { parse as parseYaml } from 'yaml'

import type { RuleEngine } from './engine.js'
import type { RuleData } from './models.js'

/** A rules file format: how to parse it, and what to call it in an error. */
export interface RuleFormat {
  name: string
  parse(text: string): unknown
}

const JSON_FORMAT: RuleFormat = { name: 'JSON', parse: (text) => JSON.parse(text) }
const YAML_FORMAT: RuleFormat = { name: 'YAML', parse: (text) => parseYaml(text) }

/** Rules file extension to format. Add new formats here. */
export const FORMATS: Record<string, RuleFormat> = {
  '.json': JSON_FORMAT,
  '.yaml': YAML_FORMAT,
  '.yml': YAML_FORMAT,
}

/**
 * Pick the format for a rules file from its extension.
 *
 * @throws If the extension has no registered format.
 */
export function getFormat(filePath: string): RuleFormat {
  const format = FORMATS[path.extname(filePath).toLowerCase()]
  if (!format) {
    throw new Error(
      `Unsupported rules file '${filePath}'. Choose from ${Object.keys(FORMATS).join(', ')}`,
    )
  }
  return format
}

/**
 * Read and parse a rules file.
 *
 * @throws If the extension is unsupported, the file cannot be read, or the
 *   contents do not parse.
 */
export function readRules(filePath: string): RuleData[] {
  const format = getFormat(filePath)
  return format.parse(fs.readFileSync(filePath, 'utf8')) as RuleData[]
}

export interface Loader {
  /**
   * Reload the rules if the source changed.
   *
   * @returns True if rules were reloaded, false if unchanged or on error.
   */
  reloadIfChanged(): boolean
}

/**
 * Loads rules from a file, re-reading it whenever its mtime changes.
 *
 * A file that has gone missing or stopped parsing is reported and then
 * ignored — the rules already in the engine stay in force.
 */
export class RulesFileLoader implements Loader {
  readonly format: RuleFormat
  #mtimeMs = 0
  #lastValid: RuleData[] = []

  constructor(
    readonly filePath: string,
    private readonly engine: RuleEngine,
    private readonly log: (message: string) => void = console.warn,
  ) {
    this.format = getFormat(filePath)
  }

  /** The rules that were last loaded successfully. */
  get lastValid(): RuleData[] {
    return this.#lastValid
  }

  reloadIfChanged(): boolean {
    let mtimeMs: number
    try {
      mtimeMs = fs.statSync(this.filePath).mtimeMs
    } catch {
      this.log(`[pproxy] ${this.filePath} not found`)
      return false
    }
    if (mtimeMs === this.#mtimeMs) return false

    let rules: RuleData[]
    try {
      rules = readRules(this.filePath)
      this.engine.load(rules)
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      this.log(`[pproxy] ${this.format.name} parse error (keeping last valid rules): ${reason}`)
      return false
    }

    this.#lastValid = rules
    this.#mtimeMs = mtimeMs
    console.log(`[pproxy] rules reloaded: ${rules.length} rules`)
    return true
  }
}

/**
 * Build a loader for a rules file.
 *
 * @throws If the extension has no registered format.
 */
export function getLoader(filePath: string, engine: RuleEngine): Loader {
  return new RulesFileLoader(filePath, engine)
}
