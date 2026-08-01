import assert from 'node:assert/strict'
import test from 'node:test'

import { POST } from '../src/app/api/graphql/route.ts'

const originalFetch = globalThis.fetch
const originalConsoleError = console.error

test.afterEach(() => {
  globalThis.fetch = originalFetch
  console.error = originalConsoleError
  delete process.env.GRAPHQL_ENDPOINT
})

test('GraphQL proxy forwards request metadata and preserves the upstream response', async () => {
  process.env.GRAPHQL_ENDPOINT = 'https://example.com/graphql/'
  let forwarded
  globalThis.fetch = async (endpoint, init) => {
    forwarded = { endpoint, init }
    return new Response('{"data":{"ok":true}}', {
      status: 201,
      headers: { 'content-type': 'application/graphql-response+json' },
    })
  }
  const request = new Request('https://example.com/api/graphql', {
    method: 'POST',
    headers: {
      authorization: 'Bearer opaque-token',
      'content-type': 'application/json; charset=utf-8',
    },
    body: '{"query":"{ ok }"}',
  })

  const response = await POST(request)

  assert.equal(forwarded.endpoint, 'https://example.com/graphql/')
  assert.equal(forwarded.init.method, 'POST')
  assert.equal(forwarded.init.cache, 'no-store')
  assert.equal(forwarded.init.headers.get('authorization'), 'Bearer opaque-token')
  assert.equal(forwarded.init.headers.get('content-type'), 'application/json; charset=utf-8')
  assert.equal(forwarded.init.body, '{"query":"{ ok }"}')
  assert.equal(response.status, 201)
  assert.equal(response.headers.get('content-type'), 'application/graphql-response+json')
  assert.equal(await response.text(), '{"data":{"ok":true}}')
})

test('GraphQL proxy applies safe content-type defaults without inventing authorization', async () => {
  globalThis.fetch = async (_endpoint, init) => {
    assert.equal(init.headers.has('authorization'), false)
    assert.equal(init.headers.get('content-type'), 'application/json')
    return new Response(null, { status: 204 })
  }
  const request = new Request('https://example.com/api/graphql', {
    method: 'POST',
    body: new TextEncoder().encode('{}'),
  })

  const response = await POST(request)

  assert.equal(response.status, 204)
  assert.equal(response.headers.get('content-type'), 'application/json')
})

test('GraphQL proxy returns a stable 502 response when the upstream is unavailable', async () => {
  const logged = []
  console.error = (...args) => logged.push(args)
  globalThis.fetch = async () => {
    throw new Error('synthetic upstream failure')
  }
  const request = new Request('https://example.com/api/graphql', {
    method: 'POST',
    body: new TextEncoder().encode('{}'),
  })

  const response = await POST(request)

  assert.equal(response.status, 502)
  assert.deepEqual(await response.json(), {
    errors: [{ message: 'GraphQL service unavailable' }],
  })
  assert.equal(logged.length, 1)
})
