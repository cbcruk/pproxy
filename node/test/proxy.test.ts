import * as fs from 'node:fs'
import * as http from 'node:http'
import * as os from 'node:os'
import * as path from 'node:path'
import * as tls from 'node:tls'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { getLocal, type Mockttp } from 'mockttp'

import { ensureCA } from '../src/ca.js'
import { RuleEngine } from '../src/engine.js'
import { RulesFileLoader } from '../src/loaders.js'
import { startProxy } from '../src/proxy.js'

interface Reply {
  status: number
  headers: http.IncomingHttpHeaders
  body: string
}

/** Make a real proxy request: absolute-form request URI, as a proxy client sends. */
function viaProxy(
  proxyPort: number,
  url: string,
  options: { method?: string; headers?: Record<string, string>; body?: string } = {},
): Promise<Reply> {
  return new Promise((resolve, reject) => {
    const target = new URL(url)
    const request = http.request(
      {
        host: '127.0.0.1',
        port: proxyPort,
        method: options.method ?? 'GET',
        path: url,
        headers: { host: target.host, ...options.headers },
      },
      (response) => {
        const chunks: Buffer[] = []
        response.on('data', (chunk: Buffer) => chunks.push(chunk))
        response.on('end', () =>
          resolve({
            status: response.statusCode ?? 0,
            headers: response.headers,
            body: Buffer.concat(chunks).toString('utf8'),
          }),
        )
      },
    )
    request.on('error', reject)
    request.end(options.body)
  })
}

/** Tunnel through the proxy with CONNECT, then speak TLS inside it. */
function viaProxyTls(proxyPort: number, host: string, urlPath: string, ca: string): Promise<Reply> {
  return new Promise((resolve, reject) => {
    const connect = http.request({
      host: '127.0.0.1',
      port: proxyPort,
      method: 'CONNECT',
      path: `${host}:443`,
    })
    connect.on('error', reject)
    connect.on('connect', (response, socket) => {
      if (response.statusCode !== 200) return reject(new Error(`CONNECT failed: ${response.statusCode}`))
      const secure = tls.connect({ socket, servername: host, ca }, () => {
        secure.write(`GET ${urlPath} HTTP/1.1\r\nHost: ${host}\r\nConnection: close\r\n\r\n`)
      })
      const chunks: Buffer[] = []
      secure.on('data', (chunk: Buffer) => chunks.push(chunk))
      secure.on('error', reject)
      secure.on('end', () => {
        const raw = Buffer.concat(chunks).toString('utf8')
        const [head, ...rest] = raw.split('\r\n\r\n')
        resolve({
          status: Number(head!.split(' ')[1]),
          headers: {},
          body: rest.join('\r\n\r\n'),
        })
      })
    })
    connect.end()
  })
}

const RULES = [
  { name: 'users', url_pattern: '*/api/users*', status_code: 200, body: { users: [], mocked: true } },
  { name: 'slow', url_pattern: '*/api/slow*', status_code: 200, body: { ok: true }, delay_ms: 300 },
  {
    name: 'user_detail',
    url_pattern: '*/graphql',
    graphql: { operation_name: 'GetUser', variables: { id: '42' } },
    status_code: 200,
    body: { data: { user: { id: '42' } } },
  },
]

describe('proxy (HTTP)', () => {
  let upstream: Mockttp
  let proxy: Mockttp
  let engine: RuleEngine

  beforeAll(async () => {
    upstream = getLocal()
    await upstream.start()
    await upstream.forAnyRequest().thenJson(200, { upstream: true })
  })

  afterAll(async () => {
    await upstream.stop()
  })

  beforeEach(async () => {
    vi.spyOn(console, 'log').mockImplementation(() => {})
    engine = new RuleEngine().load(RULES)
    proxy = await startProxy(engine, null, { host: '127.0.0.1' })
  })

  afterEach(async () => {
    await proxy.stop()
    vi.restoreAllMocks()
  })

  it('mocks a matching request', async () => {
    const reply = await viaProxy(proxy.port, `http://127.0.0.1:${upstream.port}/api/users?page=1`)
    expect(reply.status).toBe(200)
    expect(JSON.parse(reply.body)).toEqual({ users: [], mocked: true })
    expect(reply.headers['content-type']).toBe('application/json')
  })

  it('passes an unmatched request through to the real server', async () => {
    const reply = await viaProxy(proxy.port, `http://127.0.0.1:${upstream.port}/health`)
    expect(reply.status).toBe(200)
    expect(JSON.parse(reply.body)).toEqual({ upstream: true })
  })

  it('reflects the Origin on mocked responses', async () => {
    const reply = await viaProxy(proxy.port, `http://127.0.0.1:${upstream.port}/api/users`, {
      headers: { origin: 'http://localhost:3000' },
    })
    expect(reply.headers['access-control-allow-origin']).toBe('http://localhost:3000')
    expect(reply.headers['access-control-allow-credentials']).toBe('true')
  })

  it('reflects the Origin on passed-through responses too', async () => {
    const reply = await viaProxy(proxy.port, `http://127.0.0.1:${upstream.port}/health`, {
      headers: { origin: 'http://localhost:3000' },
    })
    expect(reply.headers['access-control-allow-origin']).toBe('http://localhost:3000')
  })

  it('answers a CORS preflight without a rule', async () => {
    const reply = await viaProxy(proxy.port, `http://127.0.0.1:${upstream.port}/api/users`, {
      method: 'OPTIONS',
      headers: {
        origin: 'http://localhost:3000',
        'access-control-request-method': 'POST',
        'access-control-request-headers': 'authorization',
      },
    })
    expect(reply.status).toBe(204)
    expect(reply.headers['access-control-allow-methods']).toBe('GET, POST, PUT, DELETE, PATCH, OPTIONS')
    expect(reply.headers['access-control-allow-headers']).toBe('authorization')
  })

  it('honours delay_ms', async () => {
    const started = Date.now()
    await viaProxy(proxy.port, `http://127.0.0.1:${upstream.port}/api/slow`)
    expect(Date.now() - started).toBeGreaterThanOrEqual(300)
  })

  it('matches a GraphQL operation from the request body', async () => {
    const query = 'query GetUser($id: ID!) { user(id: $id) { id } }'
    const post = (variables: Record<string, string>) =>
      viaProxy(proxy.port, `http://127.0.0.1:${upstream.port}/graphql`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ query, variables }),
      })

    expect(JSON.parse((await post({ id: '42' })).body)).toEqual({ data: { user: { id: '42' } } })
    // A different id matches no rule, so it reaches the real server.
    expect(JSON.parse((await post({ id: '7' })).body)).toEqual({ upstream: true })
  })

  it('fires engine hooks, which is what `run --verbose` logs with', async () => {
    await proxy.stop()
    const seen: Array<[string, string]> = []
    const hooked = new RuleEngine().load(RULES)
    hooked.addHook((url, rule) => seen.push([url, rule.name]))
    proxy = await startProxy(hooked, null, { host: '127.0.0.1' })

    await viaProxy(proxy.port, `http://127.0.0.1:${upstream.port}/api/users`)
    await viaProxy(proxy.port, `http://127.0.0.1:${upstream.port}/health`)
    expect(seen).toEqual([[`http://127.0.0.1:${upstream.port}/api/users`, 'users']])
  })

  it('reports interceptions through onIntercept', async () => {
    await proxy.stop()
    const seen: Array<[string, number]> = []
    proxy = await startProxy(engine, null, {
      host: '127.0.0.1',
      onIntercept: (url, mock) => seen.push([url, mock.statusCode]),
    })
    await viaProxy(proxy.port, `http://127.0.0.1:${upstream.port}/api/users`)
    await viaProxy(proxy.port, `http://127.0.0.1:${upstream.port}/health`)
    expect(seen).toEqual([[`http://127.0.0.1:${upstream.port}/api/users`, 200]])
  })
})

describe('proxy (hot reload)', () => {
  let dir: string
  let proxy: Mockttp

  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pproxy-proxy-'))
    vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(async () => {
    await proxy?.stop()
    vi.restoreAllMocks()
    fs.rmSync(dir, { recursive: true, force: true })
  })

  it('serves an edited rules file without a restart', async () => {
    const file = path.join(dir, 'rules.json')
    fs.writeFileSync(file, JSON.stringify([{ url_pattern: '*/api/*', body: { version: 1 } }]))

    const engine = new RuleEngine()
    const loader = new RulesFileLoader(file, engine, () => {})
    loader.reloadIfChanged()
    proxy = await startProxy(engine, loader, { host: '127.0.0.1' })

    const before = await viaProxy(proxy.port, 'http://example.test/api/x')
    expect(JSON.parse(before.body)).toEqual({ version: 1 })

    fs.writeFileSync(file, JSON.stringify([{ url_pattern: '*/api/*', body: { version: 2 } }]))
    const ahead = new Date(Date.now() + 2000)
    fs.utimesSync(file, ahead, ahead)

    const after = await viaProxy(proxy.port, 'http://example.test/api/x')
    expect(JSON.parse(after.body)).toEqual({ version: 2 })
  })
})

describe('proxy (HTTPS via CONNECT)', () => {
  let proxy: Mockttp
  let dir: string
  let cert: string

  beforeAll(async () => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pproxy-ca-'))
    const ca = await ensureCA(dir)
    cert = fs.readFileSync(ca.certPath, 'utf8')
    vi.spyOn(console, 'log').mockImplementation(() => {})
    proxy = await startProxy(new RuleEngine().load(RULES), null, {
      host: '127.0.0.1',
      https: { keyPath: ca.keyPath, certPath: ca.certPath },
    })
  }, 30_000)

  afterAll(async () => {
    await proxy.stop()
    vi.restoreAllMocks()
    fs.rmSync(dir, { recursive: true, force: true })
  })

  it('intercepts inside the TLS tunnel with a certificate from our CA', async () => {
    const reply = await viaProxyTls(proxy.port, 'api.example.com', '/api/users', cert)
    expect(reply.status).toBe(200)
    expect(JSON.parse(reply.body)).toEqual({ users: [], mocked: true })
  })

  it('matches on the full https URL, not just the path', async () => {
    const reply = await viaProxyTls(proxy.port, 'api.example.com', '/health', cert)
    // No rule matches, so the proxy tries the real api.example.com and fails
    // to reach it — proving the request left the mock path.
    expect(reply.status).toBeGreaterThanOrEqual(500)
  })
})

describe('proxy (binding)', () => {
  it('listens only on the requested host', async () => {
    const external = Object.values(os.networkInterfaces())
      .flat()
      .find((iface) => iface && iface.family === 'IPv4' && !iface.internal)
    if (!external) return // no non-loopback interface to prove it with

    vi.spyOn(console, 'log').mockImplementation(() => {})
    const proxy = await startProxy(new RuleEngine().load(RULES), null, { host: '127.0.0.1' })
    try {
      await expect(
        new Promise((resolve, reject) => {
          const socket = http
            .get({ host: external.address, port: proxy.port, path: '/' }, resolve)
            .on('error', reject)
          socket.setTimeout(2000, () => reject(new Error('timed out')))
        }),
      ).rejects.toThrow()
    } finally {
      await proxy.stop()
      vi.restoreAllMocks()
    }
  })
})
