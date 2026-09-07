/**
 * CA certificate management.
 *
 * Intercepting HTTPS means terminating TLS, which means the client has to
 * trust a certificate we sign. mockttp generates that CA for us; this module
 * keeps it on disk next to the rest of pproxy's runtime state and wraps the
 * macOS commands that add it to (and remove it from) the system trust store.
 */

import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { spawnSync } from 'node:child_process'
import { generateCACertificate } from 'mockttp'

/** Where pproxy keeps its config and runtime files, shared with the SwiftBar plugin. */
export function runtimeDir(): string {
  const base = process.env['XDG_CONFIG_HOME'] || path.join(os.homedir(), '.config')
  return path.join(base, 'pproxy')
}

export interface CAPaths {
  keyPath: string
  certPath: string
}

/** Paths to the CA private key and certificate. */
export function caPaths(dir: string = runtimeDir()): CAPaths {
  return {
    keyPath: path.join(dir, 'ca-key.pem'),
    certPath: path.join(dir, 'ca-cert.pem'),
  }
}

/**
 * Return the CA paths, generating the certificate on first use.
 *
 * The CA is reused across runs so the certificate only has to be trusted
 * once. The private key is written user-readable only.
 */
export async function ensureCA(dir: string = runtimeDir()): Promise<CAPaths & { created: boolean }> {
  const paths = caPaths(dir)
  if (fs.existsSync(paths.certPath) && fs.existsSync(paths.keyPath)) {
    return { ...paths, created: false }
  }

  const { key, cert } = await generateCACertificate({
    subject: { commonName: 'pproxy CA', organizationName: 'pproxy' },
  })
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(paths.keyPath, key, { mode: 0o600 })
  fs.writeFileSync(paths.certPath, cert)
  return { ...paths, created: true }
}

/** The `security` invocation that trusts (or untrusts) the CA on macOS. */
export function trustCommand(certPath: string, action: 'install' | 'uninstall'): string[] {
  return action === 'install'
    ? [
        'sudo',
        'security',
        'add-trusted-cert',
        '-d',
        '-r',
        'trustRoot',
        '-k',
        '/Library/Keychains/System.keychain',
        certPath,
      ]
    : ['sudo', 'security', 'remove-trusted-cert', '-d', certPath]
}

/**
 * Add the CA to (or remove it from) the macOS system trust store.
 *
 * Runs with the caller's stdio attached so `sudo` can prompt for a password.
 *
 * @returns The process exit status.
 */
export function trustCA(certPath: string, action: 'install' | 'uninstall'): number {
  const [command, ...args] = trustCommand(certPath, action)
  const result = spawnSync(command!, args, { stdio: 'inherit' })
  if (result.error) throw result.error
  return result.status ?? 1
}
