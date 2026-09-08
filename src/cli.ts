#!/usr/bin/env node
/**
 * The `pproxy` command.
 *
 * Ported from `archive/python/src/pproxy/cli.py`, plus a `cert` command — mockttp keeps its
 * CA as ordinary files, so trusting it can be scripted instead of walked
 * through by hand.
 */

import * as fs from 'node:fs'

import { RuleEngine } from './engine.js'
import { getLoader, readRules, type Loader } from './loaders.js'
import { getMatcher } from './matching.js'
import { startProxy } from './proxy.js'
import { caPaths, ensureCA, trustCA, trustCommand } from './ca.js'

/** Loopback, so a MITM proxy is not exposed to the network by default. */
const DEFAULT_HOST = '127.0.0.1'
/** Conventional local proxy port. */
const DEFAULT_PORT = 8080

/** Help text for `-h`, and for an unrecognized command. */
const USAGE = `usage: pproxy <command> [options]

URL pattern-based HTTP response interceptor.

commands:
  run <rules>       start the intercepting proxy
    -H, --host HOST   listen host (default: ${DEFAULT_HOST})
    -p, --port PORT   listen port (default: ${DEFAULT_PORT})
    -v, --verbose     log every intercepted request
    --http-only       skip HTTPS interception (no CA needed)
  check <rules>     validate a rules file and exit
  cert <action>     manage the HTTPS CA — path | install | uninstall
`

/** The parsed command line, shared by every subcommand. */
interface Options {
  /** Interface to bind, from `-H`/`--host`. */
  host: string
  /** Port to listen on, from `-p`/`--port`. */
  port: number
  /** Log every interception, from `-v`/`--verbose`. */
  verbose: boolean
  /** Skip HTTPS interception, from `--http-only`. Needs no CA. */
  httpOnly: boolean
  /** Arguments that are not flags — the rules file, or the `cert` action. */
  positional: string[]
}

/**
 * Parse the flags this CLI accepts. Unknown flags are an error.
 *
 * @param argv Arguments after the subcommand name.
 * @throws If a flag is unrecognized, missing its value, or the port is not in
 * 0–65535.
 */
export function parseArgs(argv: string[]): Options {
  const options: Options = {
    host: DEFAULT_HOST,
    port: DEFAULT_PORT,
    verbose: false,
    httpOnly: false,
    positional: [],
  }

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]!
    switch (arg) {
      case '-H':
      case '--host':
        options.host = expectValue(argv, (i += 1), arg)
        break
      case '-p':
      case '--port': {
        const raw = expectValue(argv, (i += 1), arg)
        const port = Number(raw)
        if (!Number.isInteger(port) || port < 0 || port > 65535) {
          throw new Error(`${arg}: invalid port ${raw}`)
        }
        options.port = port
        break
      }
      case '-v':
      case '--verbose':
        options.verbose = true
        break
      case '--http-only':
        options.httpOnly = true
        break
      default:
        if (arg.startsWith('-')) throw new Error(`unrecognized argument: ${arg}`)
        options.positional.push(arg)
    }
  }
  return options
}

/**
 * Read the value that follows a flag.
 *
 * @throws If the flag was the last argument.
 */
function expectValue(argv: string[], index: number, flag: string): string {
  const value = argv[index]
  if (value === undefined) throw new Error(`${flag}: expected a value`)
  return value
}

/**
 * Build an engine and loader for a rules file, and do the initial load.
 *
 * The initial load goes through the loader, so a rules file that does not parse
 * leaves an empty engine and logs the reason rather than throwing.
 *
 * @throws If the file's extension has no registered format.
 */
export function loadEngine(rulesPath: string): { engine: RuleEngine; loader: Loader } {
  const engine = new RuleEngine()
  const loader = getLoader(rulesPath, engine)
  loader.reloadIfChanged()
  return { engine, loader }
}

/**
 * `pproxy run` — start the proxy and block until SIGINT or SIGTERM.
 *
 * @returns The process exit code: 0 on clean shutdown, 1 when the rules file is
 * missing or unloadable, 2 when it was not given.
 */
async function runCommand(options: Options): Promise<number> {
  const rulesPath = options.positional[0]
  if (!rulesPath) {
    console.error('run: missing rules file')
    return 2
  }
  if (!fs.existsSync(rulesPath)) {
    console.error(`${rulesPath} not found`)
    return 1
  }

  let engine: RuleEngine
  let loader: Loader
  try {
    ;({ engine, loader } = loadEngine(rulesPath))
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error))
    return 1
  }

  if (options.verbose) {
    engine.addHook((url, rule) => console.log(`[pproxy] ${url} → ${rule.name || rule.pattern}`))
  }

  const https = options.httpOnly ? undefined : await ensureCA()
  if (https?.created) console.log(`[pproxy] generated CA — trust it with: pproxy cert install`)

  const server = await startProxy(engine, loader, {
    host: options.host,
    port: options.port,
    https: https ? { keyPath: https.keyPath, certPath: https.certPath } : undefined,
    onIntercept: (url, mock) =>
      console.log(`[pproxy] intercepted: ${url} → ${mock.statusCode}`),
  })

  console.log(`[pproxy] listening on ${options.host}:${server.port} — rules: ${rulesPath}`)
  if (options.httpOnly) console.log('[pproxy] HTTPS interception disabled (--http-only)')

  await new Promise<void>((resolve) => {
    const shutdown = () => {
      void server.stop().then(resolve)
    }
    process.once('SIGINT', shutdown)
    process.once('SIGTERM', shutdown)
  })
  return 0
}

/**
 * `pproxy check` — load a rules file, print each rule, and validate it.
 *
 * Reads without the loader's keep-last-valid safety net, since reporting
 * exactly what is wrong is the point of the command.
 *
 * @returns The process exit code: 0 when every rule is valid, 1 when the file
 * is missing, unloadable, empty, or names an unknown matcher, 2 when no file
 * was given.
 */
export function checkCommand(options: Options): number {
  const rulesPath = options.positional[0]
  if (!rulesPath) {
    console.error('check: missing rules file')
    return 2
  }
  if (!fs.existsSync(rulesPath)) {
    console.error(`${rulesPath} not found`)
    return 1
  }

  const engine = new RuleEngine()
  try {
    engine.load(readRules(rulesPath))
  } catch (error) {
    console.error(`failed to load ${rulesPath}: ${error instanceof Error ? error.message : error}`)
    return 1
  }

  const rules = engine.rules
  if (rules.length === 0) {
    console.error(`no rules loaded from ${rulesPath}`)
    return 1
  }

  let failed = false
  for (const rule of rules) {
    try {
      getMatcher(rule.matcher)
    } catch (error) {
      console.error(`  ${rule.pattern}: ${error instanceof Error ? error.message : error}`)
      failed = true
      continue
    }
    const label = rule.name ? ` (${rule.name})` : ''
    const condition = rule.graphql ? ` graphql:${rule.graphql.describe()}` : ''
    console.log(
      `  ${rule.matcher.padEnd(5)} ${rule.pattern}${condition} → ${rule.response.statusCode}${label}`,
    )
  }

  if (failed) return 1
  console.log(`${rules.length} rules OK`)
  return 0
}

/**
 * `pproxy cert` — print the CA path, or trust/untrust it on macOS.
 *
 * @returns The process exit code: `security`'s own status for install and
 * uninstall, 1 when the certificate does not exist yet or the platform is not
 * macOS, 2 for an unknown action.
 */
async function certCommand(options: Options): Promise<number> {
  const action = options.positional[0] ?? 'path'

  if (action === 'path') {
    const { certPath, keyPath } = caPaths()
    console.log(certPath)
    if (!fs.existsSync(certPath)) {
      console.error('(not generated yet — it is created on the first `pproxy run`)')
      return 1
    }
    console.error(`key: ${keyPath}`)
    return 0
  }

  if (action !== 'install' && action !== 'uninstall') {
    console.error(`cert: unknown action '${action}'. Choose from path, install, uninstall`)
    return 2
  }

  const { certPath } = await ensureCA()
  if (process.platform !== 'darwin') {
    console.error(`cert ${action} automates macOS only. Trust this file by hand:\n  ${certPath}`)
    return 1
  }

  console.log(`$ ${trustCommand(certPath, action).join(' ')}`)
  return trustCA(certPath, action)
}

/**
 * Dispatch a command line to its subcommand.
 *
 * Returns an exit code rather than calling `process.exit`, so tests can drive
 * the whole CLI in-process.
 *
 * @param argv Full argument list; defaults to the real one.
 * @returns The process exit code. 2 covers usage errors, including a bare
 * invocation with no command.
 */
export async function main(argv: string[] = process.argv.slice(2)): Promise<number> {
  const [command, ...rest] = argv
  if (!command || command === '-h' || command === '--help') {
    console.log(USAGE)
    return command ? 0 : 2
  }

  let options: Options
  try {
    options = parseArgs(rest)
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error))
    return 2
  }

  switch (command) {
    case 'run':
      return runCommand(options)
    case 'check':
      return checkCommand(options)
    case 'cert':
      return certCommand(options)
    default:
      console.error(`unknown command: ${command}\n`)
      console.error(USAGE)
      return 2
  }
}

/** True when run as `pproxy`, false when imported by a test. */
const invokedDirectly = process.argv[1] && import.meta.url === `file://${process.argv[1]}`
if (invokedDirectly) {
  main().then(
    (code) => process.exit(code),
    (error) => {
      console.error(error)
      process.exit(1)
    },
  )
}
