import assert from 'node:assert/strict'
import { test } from 'vitest'

test('browser GraphQL client resolves endpoints, authenticates, retries, and disables caching', async () => {
  const originalWindow = globalThis.window
  const originalFetch = globalThis.fetch
  const originalSetTimeout = globalThis.setTimeout
  const originalWarn = console.warn
  const originalEndpoint = process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT
  const warnings = []

  console.warn = (...args) => warnings.push(args)
  globalThis.setTimeout = (callback) => {
    callback()
    return 1
  }

  try {
    const client = await import('../src/lib/graphql.ts')

    globalThis.window = { location: { origin: 'https://example.com' } }
    delete process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT
    const authenticatedCalls = []
    globalThis.fetch = async (input, init) => {
      authenticatedCalls.push([input, init])
      if (String(input).includes('/api/auth/session')) {
        return Response.json({ accessToken: 'opaque-token', expires: '2099-01-01' })
      }
      return Response.json({ data: { ok: true } })
    }

    assert.deepEqual(await client.graphqlRequest('query Test', { id: 1 }), { ok: true })
    const [url, request] = authenticatedCalls.at(-1)
    assert.equal(String(url), 'https://example.com/graphql/')
    assert.equal(request.cache, 'no-store')
    assert.equal(new Headers(request.headers).get('Authorization'), 'Bearer opaque-token')
    assert.match(String(request.body), /query Test/)
    assert.equal(client.gql`query ${'Name'}`, 'query Name')

    delete globalThis.window
    process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT = 'https://example.com/graphql/'
    const sessionPayloads = [
      {},
      { user: {}, expires: '2099-01-01' },
      {},
      {},
    ]
    const anonymousCalls = []
    globalThis.fetch = async (input, init) => {
      if (String(input).includes('/api/auth/session')) {
        return Response.json(sessionPayloads.shift())
      }
      anonymousCalls.push([input, init])
      return Response.json({ data: { ok: true } })
    }

    assert.deepEqual(await client.graphqlRequest('query Retry'), { ok: true })
    assert.deepEqual(warnings.at(-1)[1], { hasSession: true })
    assert.deepEqual(await client.graphqlRequest('query Anonymous'), { ok: true })
    assert.deepEqual(warnings.at(-1)[1], { hasSession: false })
    assert.equal(String(anonymousCalls.at(-1)[0]), 'https://example.com/graphql/')
    assert.equal(anonymousCalls.at(-1)[1].cache, 'no-store')

    globalThis.fetch = async (input) => {
      if (String(input).includes('/api/auth/session')) {
        return Response.json({ accessToken: 'opaque-token', expires: '2099-01-01' })
      }
      throw new Error('network unavailable')
    }
    await assert.rejects(client.graphqlRequest('query Failure'), /network unavailable/)
  } finally {
    globalThis.window = originalWindow
    globalThis.fetch = originalFetch
    globalThis.setTimeout = originalSetTimeout
    console.warn = originalWarn
    if (originalEndpoint === undefined) {
      delete process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT
    } else {
      process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT = originalEndpoint
    }
  }
})
