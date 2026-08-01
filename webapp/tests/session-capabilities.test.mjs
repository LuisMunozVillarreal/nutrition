import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

async function loadCapabilities() {
  return import('../src/lib/sessionCapabilities.ts')
}

test('JWT capability callback records the staff capability at sign-in without refreshing it', async () => {
  const { createJwtCapabilityCallback } = await loadCapabilities()
  let refreshCalls = 0
  const jwt = createJwtCapabilityCallback(
    async () => {
      refreshCalls += 1
      return { authentication: 'authenticated', isStaff: false }
    },
    { now: () => 1_000 },
  )

  const token = await jwt({
    token: {},
    user: { accessToken: 'opaque-token', isStaff: true },
  })

  assert.equal(token.isStaff, true)
  assert.equal(token.staffCapabilityRefreshedAt, 1_000)
  assert.equal(refreshCalls, 0)
})

test('JWT capability callback avoids refreshes inside the interval and revokes staff when due', async () => {
  const { createJwtCapabilityCallback, STAFF_CAPABILITY_REFRESH_INTERVAL_MS } =
    await loadCapabilities()
  let now = 2_000
  let refreshCalls = 0
  const jwt = createJwtCapabilityCallback(
    async () => {
      refreshCalls += 1
      return { authentication: 'authenticated', isStaff: false }
    },
    { now: () => now },
  )

  let token = await jwt({
    token: {},
    user: { accessToken: 'opaque-token', isStaff: true },
  })
  now += STAFF_CAPABILITY_REFRESH_INTERVAL_MS - 1
  token = await jwt({ token })

  assert.equal(token.isStaff, true)
  assert.equal(refreshCalls, 0)

  now += 1
  token = await jwt({ token })

  assert.equal(token.isStaff, false)
  assert.equal(token.staffCapabilityRefreshedAt, now)
  assert.equal(refreshCalls, 1)
})

test('JWT capability callback promotes a regular user when the refresh reports staff', async () => {
  const { createJwtCapabilityCallback, STAFF_CAPABILITY_REFRESH_INTERVAL_MS } =
    await loadCapabilities()
  let now = 3_000
  const jwt = createJwtCapabilityCallback(
    async () => ({ authentication: 'authenticated', isStaff: true }),
    { now: () => now },
  )

  let token = await jwt({
    token: {},
    user: { accessToken: 'opaque-token', isStaff: false },
  })
  now += STAFF_CAPABILITY_REFRESH_INTERVAL_MS
  token = await jwt({ token })

  assert.equal(token.isStaff, true)
  assert.equal(token.staffCapabilityRefreshedAt, now)
})

test('JWT capability callback fails closed and bounds retries after refresh failure', async () => {
  const { createJwtCapabilityCallback, STAFF_CAPABILITY_REFRESH_INTERVAL_MS } =
    await loadCapabilities()
  let now = 4_000
  let refreshCalls = 0
  const jwt = createJwtCapabilityCallback(
    async () => {
      refreshCalls += 1
      throw new Error('capability refresh unavailable')
    },
    { now: () => now },
  )

  let token = await jwt({
    token: {},
    user: { accessToken: 'opaque-token', isStaff: true },
  })
  now += STAFF_CAPABILITY_REFRESH_INTERVAL_MS
  token = await jwt({ token })
  token = await jwt({ token })

  assert.equal(token.isStaff, false)
  assert.equal(token.accessToken, 'opaque-token')
  assert.equal(token.error, undefined)
  assert.equal(token.staffCapabilityRefreshedAt, now)
  assert.equal(refreshCalls, 1)
})

test('unauthorized backend me clears the token and remains reauthentication-required across callbacks', async () => {
  const {
    applyTokenCapabilitiesToSession,
    BACKEND_REAUTHENTICATION_REQUIRED,
    createJwtCapabilityCallback,
    STAFF_CAPABILITY_REFRESH_INTERVAL_MS,
  } = await loadCapabilities()
  let now = 4_500
  let refreshCalls = 0
  const jwt = createJwtCapabilityCallback(
    async () => {
      refreshCalls += 1
      return { authentication: 'unauthenticated' }
    },
    { now: () => now },
  )

  let token = await jwt({
    token: {},
    user: { accessToken: 'expired-backend-token', isStaff: true },
  })
  now += STAFF_CAPABILITY_REFRESH_INTERVAL_MS
  token = await jwt({ token })
  token = await jwt({ token })
  token = await jwt({ token })

  assert.equal(token.accessToken, undefined)
  assert.equal(token.isStaff, false)
  assert.equal(token.error, BACKEND_REAUTHENTICATION_REQUIRED)
  assert.equal(refreshCalls, 1)

  const session = applyTokenCapabilitiesToSession(
    { accessToken: 'stale-session-token', user: { name: 'User' } },
    token,
  )
  assert.equal(session.accessToken, undefined)
  assert.equal(session.user.isStaff, false)
  assert.equal(session.error, BACKEND_REAUTHENTICATION_REQUIRED)
})

test('refreshed staff capability propagates from repeated JWT callbacks to the session', async () => {
  const {
    applyTokenCapabilitiesToSession,
    createJwtCapabilityCallback,
    STAFF_CAPABILITY_REFRESH_INTERVAL_MS,
  } = await loadCapabilities()
  let now = 5_000
  const jwt = createJwtCapabilityCallback(
    async () => ({ authentication: 'authenticated', isStaff: true }),
    { now: () => now },
  )

  let token = await jwt({
    token: {},
    user: { accessToken: 'opaque-token', isStaff: false },
  })
  now += STAFF_CAPABILITY_REFRESH_INTERVAL_MS
  token = await jwt({ token })
  const session = applyTokenCapabilitiesToSession({ user: { name: 'User' } }, token)

  assert.equal(session.user.isStaff, true)
  assert.equal(session.accessToken, 'opaque-token')
})

test('regular login remains least privilege through JWT and session callbacks', async () => {
  const { applyUserCapabilitiesToToken, applyTokenCapabilitiesToSession } =
    await loadCapabilities()
  const token = applyUserCapabilitiesToToken({}, {
    accessToken: 'opaque-token',
    isStaff: false,
  })
  const session = applyTokenCapabilitiesToSession({ user: { name: 'Regular' } }, token)

  assert.equal(token.isStaff, false)
  assert.equal(session.user.isStaff, false)
})

test('staff login retains staff capability through JWT and session callbacks', async () => {
  const { applyUserCapabilitiesToToken, applyTokenCapabilitiesToSession } =
    await loadCapabilities()
  const token = applyUserCapabilitiesToToken({}, {
    accessToken: 'opaque-token',
    isStaff: true,
  })
  const session = applyTokenCapabilitiesToSession({ user: { name: 'Staff' } }, token)

  assert.equal(token.isStaff, true)
  assert.equal(session.user.isStaff, true)
})

test('capability helpers preserve anonymous tokens and clear stale session fields', async () => {
  const {
    applyUserCapabilitiesToToken,
    applyTokenCapabilitiesToSession,
    createJwtCapabilityCallback,
  } = await loadCapabilities()
  const originalToken = { marker: 'preserved' }

  assert.equal(applyUserCapabilitiesToToken(originalToken, null), originalToken)

  const jwt = createJwtCapabilityCallback(async () => {
    throw new Error('anonymous tokens must not be refreshed')
  })
  const anonymousToken = await jwt({ token: {} })
  assert.equal(anonymousToken.isStaff, false)

  const session = applyTokenCapabilitiesToSession(
    {
      accessToken: 'stale-token',
      error: 'BackendReauthenticationRequired',
      user: null,
    },
    { isStaff: false },
  )
  assert.equal(session.accessToken, undefined)
  assert.equal(session.error, undefined)
  assert.deepEqual(session.user, { isStaff: false })
})

test('capability refresh runs when the recorded timestamp is in the future', async () => {
  const { createJwtCapabilityCallback } = await loadCapabilities()
  let refreshCalls = 0
  const jwt = createJwtCapabilityCallback(
    async () => {
      refreshCalls += 1
      return { authentication: 'authenticated', isStaff: true }
    },
    { now: () => 10 },
  )

  const token = await jwt({
    token: {
      accessToken: 'opaque-token',
      isStaff: false,
      staffCapabilityRefreshedAt: 11,
      error: 'BackendReauthenticationRequired',
    },
  })

  assert.equal(refreshCalls, 1)
  assert.equal(token.isStaff, true)
  assert.equal(token.error, undefined)
})

test('NextAuth refreshes and propagates the backend staff capability', async () => {
  const route = await readFile(
    new URL('../src/app/api/auth/[...nextauth]/route.ts', import.meta.url),
    'utf8',
  )
  const authHelpers = await readFile(
    new URL('../src/lib/auth.ts', import.meta.url),
    'utf8',
  )
  const declarations = await readFile(
    new URL('../types/next-auth.d.ts', import.meta.url),
    'utf8',
  )

  assert.match(authHelpers, /me\s*\{\s*isStaff\s*\}/)
  assert.match(authHelpers, /Authorization:\s*`Bearer \$\{accessToken\}`/)
  assert.match(route, /createJwtCapabilityCallback/)
  assert.match(route, /fetchCurrentStaffCapability/)
  assert.match(route, /jwtCapabilityCallback\(\{ token, user \}\)/)
  assert.match(route, /applyTokenCapabilitiesToSession\(session, token\)/)
  assert.match(declarations, /isStaff:\s*boolean/)
  assert.match(declarations, /staffCapabilityRefreshedAt\?:\s*number/)
})
