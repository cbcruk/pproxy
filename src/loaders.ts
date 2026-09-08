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
  /** Display name, used in parse-error messages. */
  name: string
  /**
   * Parse the file's text. Returns `unknown` because a rules file is arbitrary
   * user input until {@link RuleEngine.load} validates it.
   */
  parse(text: string): unknown
}

/** The `.json` format. */
const JSON_FORMAT: RuleFormat = { name: 'JSON', parse: (text) => JSON.parse(text) }
/** The `.yaml` and `.yml` formats, which share one parser. */
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

/**
 * A source of rules that can be re-checked for changes.
 *
 * The proxy polls this on every request, so an implementation must be cheap
 * when nothing has changed.
 */
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
  /** The format resolved from the file's extension, fixed at construction. */
  readonly format: RuleFormat
  /** mtime of the last successful read, used to skip unchanged files. */
  #mtimeMs = 0
  /** The last rules that parsed, kept so a broken edit changes nothing. */
  #lastValid: RuleData[] = []

  /**
   * @param filePath Rules file to watch.
   * @param engine Engine to load the rules into on every successful read.
   * @param log Where parse failures are reported; defaults to `console.warn`.
   * @throws If the file's extension has no registered format.
   */
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

  /**
   * Re-read the file when its mtime has moved, and load the result.
   *
   * Never throws: a missing file or a parse error is logged and reported as
   * `false`, leaving the rules already in the engine untouched. That is what
   * keeps a half-typed edit from taking the proxy down.
   *
   * @returns True when rules were reloaded, false when unchanged or on error.
   */
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
