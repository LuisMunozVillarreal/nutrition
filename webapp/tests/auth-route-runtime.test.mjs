import assert from 'node:assert/strict'
import { after, mock, test } from 'node:test'

const originalEndpoint = process.env.GRAPHQL_ENDPOINT
const clients = []
const responses = []
const handler = mock.fn()
let capturedOptions

await mock.module('next-auth', {
  defaultExport: (options) => {
    capturedOptions = options
    return handler
  },
})
await mock.module('next-auth/providers/credentials', {
  defaultExport: (options) => options,
})
await mock.module('graphql-request', {
  namedExports: {
    GraphQLClient: class {
      constructor(endpoint) {
        this.endpoint = endpoint
        this.requests = []
        clients.push(this)
      }

      async request(...args) {
        this.requests.push(args)
        const response = responses.shift()
        return typeof response === 'function' ? response(...args) : response
      }
    },
  },
})

after(() => {
  if (originalEndpoint === undefined) delete process.env.GRAPHQL_ENDPOINT
  else process.env.GRAPHQL_ENDPOINT = originalEndpoint
})

test('NextAuth route wires credentials, capability refresh, sessions, handlers, and endpoints', async () => {
  delete process.env.GRAPHQL_ENDPOINT
  const defaultRoute = await import('../.coverage-src/app/api/auth/[...nextauth]/route.js?default-endpoint')
  assert.equal(clients[0].endpoint, 'http://localhost:8000/graphql/')
  assert.equal(defaultRoute.GET, handler)
  assert.equal(defaultRoute.POST, handler)
  assert.equal(defaultRoute.authOptions.session.maxAge, 24 * 60 * 60)
  assert.equal(defaultRoute.authOptions.jwt.maxAge, 24 * 60 * 60)
  assert.equal(defaultRoute.authOptions.pages.signIn, '/login')

  const provider = defaultRoute.authOptions.providers[0]
  assert.equal(provider.name, 'Credentials')
  assert.deepEqual(provider.credentials, {
    email: { label: 'Email', type: 'email' },
    password: { label: 'Password', type: 'password' },
  })

  responses.push({
    login: {
      token: 'opaque-token',
      user: { id: 'u1', email: 'user@example.com', firstName: 'Test', lastName: 'User', isStaff: true },
    },
  })
  assert.deepEqual(await provider.authorize({ email: 'user@example.com', password: 'not-a-real-secret' }), {
    id: 'u1',
    email: 'user@example.com',
    name: 'Test User',
    accessToken: 'opaque-token',
    isStaff: true,
  })
  assert.equal(clients[0].requests[0][1].email, 'user@example.com')

  const initialToken = await defaultRoute.authOptions.callbacks.jwt({
    token: {},
    user: { accessToken: 'opaque-token', isStaff: true },
  })
  assert.equal(initialToken.accessToken, 'opaque-token')
  assert.equal(initialToken.isStaff, true)

  responses.push({ me: { isStaff: false } })
  const refreshedToken = await defaultRoute.authOptions.callbacks.jwt({
    token: { accessToken: 'opaque-token' },
  })
  assert.equal(refreshedToken.isStaff, false)
  assert.equal(clients[0].requests.at(-1)[2].Authorization, 'Bearer opaque-token')

  assert.deepEqual(await defaultRoute.authOptions.callbacks.session({
    session: { user: { name: 'Test User' } },
    token: refreshedToken,
  }), {
    accessToken: 'opaque-token',
    user: { name: 'Test User', isStaff: false },
  })

  process.env.GRAPHQL_ENDPOINT = 'https://api.example.com/graphql/'
  const configuredRoute = await import('../.coverage-src/app/api/auth/[...nextauth]/route.js?configured-endpoint')
  assert.equal(clients[1].endpoint, 'https://api.example.com/graphql/')
  assert.equal(configuredRoute.GET, handler)
  assert.equal(capturedOptions, configuredRoute.authOptions)
})
