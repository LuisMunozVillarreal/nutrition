import assert from 'node:assert/strict'
import test from 'node:test'

async function loadAuthHelpers() {
  return import('../src/lib/auth.ts')
}

test('successful credential authorization returns the NextAuth user', async () => {
  const { authorizeCredentials } = await loadAuthHelpers()
  const result = await authorizeCredentials(
    { email: 'user@example.com', password: 'synthetic-password' },
    async () => ({
      login: {
        token: 'opaque-token',
        user: {
          id: 'user-id',
          email: 'user@example.com',
          firstName: 'Test',
          lastName: 'User',
          isStaff: true,
        },
      },
    }),
  )

  assert.deepEqual(result, {
    id: 'user-id',
    email: 'user@example.com',
    name: 'Test User',
    accessToken: 'opaque-token',
    isStaff: true,
  })
})

test('staff capability refresh queries me with the bearer access token', async () => {
  const { fetchCurrentStaffCapability } = await loadAuthHelpers()
  let receivedRequest

  const capability = await fetchCurrentStaffCapability(
    'opaque-token',
    async (document, variables, requestHeaders) => {
      receivedRequest = { document, variables, requestHeaders }
      return { me: { isStaff: true } }
    },
  )

  assert.deepEqual(capability, { authentication: 'authenticated', isStaff: true })
  assert.match(receivedRequest.document, /me\s*\{\s*isStaff\s*\}/)
  assert.deepEqual(receivedRequest.variables, {})
  assert.deepEqual(receivedRequest.requestHeaders, {
    Authorization: 'Bearer opaque-token',
  })
})

test('staff capability distinguishes a genuine regular user from an unauthenticated token', async () => {
  const { fetchCurrentStaffCapability } = await loadAuthHelpers()

  const regular = await fetchCurrentStaffCapability(
    'regular-token',
    async () => ({ me: { isStaff: false } }),
  )
  const unauthenticated = await fetchCurrentStaffCapability(
    'expired-token',
    async () => ({ me: null }),
  )

  assert.deepEqual(regular, {
    authentication: 'authenticated',
    isStaff: false,
  })
  assert.deepEqual(unauthenticated, { authentication: 'unauthenticated' })
})

test('failed credential authorization returns null without exposing request secrets in logs', async () => {
  const { authorizeCredentials } = await loadAuthHelpers()
  const sentinels = [
    'credential-email-sentinel@example.com',
    'credential-password-sentinel',
    'authorization-header-sentinel',
    'request-body-sentinel',
  ]
  const logged = []
  const originalConsole = {
    error: console.error,
    log: console.log,
    warn: console.warn,
  }
  console.error = (...args) => logged.push(args)
  console.log = (...args) => logged.push(args)
  console.warn = (...args) => logged.push(args)

  try {
    const credentialBearingError = Object.assign(
      new Error(`request failed for ${sentinels[0]} with ${sentinels[1]}`),
      {
        request: {
          body: sentinels[3],
          headers: { authorization: sentinels[2] },
          variables: { email: sentinels[0], password: sentinels[1] },
        },
      },
    )
    const result = await authorizeCredentials(
      { email: sentinels[0], password: sentinels[1] },
      async () => {
        throw credentialBearingError
      },
    )

    assert.equal(result, null)
    const renderedLogs = JSON.stringify(logged)
    for (const sentinel of sentinels) {
      assert.equal(renderedLogs.includes(sentinel), false)
    }
  } finally {
    console.error = originalConsole.error
    console.log = originalConsole.log
    console.warn = originalConsole.warn
  }
})
