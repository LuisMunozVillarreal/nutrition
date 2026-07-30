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
      return false
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
      return false
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
  const jwt = createJwtCapabilityCallback(async () => true, { now: () => now })

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
  assert.equal(token.staffCapabilityRefreshedAt, now)
  assert.equal(refreshCalls, 1)
})

test('refreshed staff capability propagates from repeated JWT callbacks to the session', async () => {
  const {
    applyTokenCapabilitiesToSession,
    createJwtCapabilityCallback,
    STAFF_CAPABILITY_REFRESH_INTERVAL_MS,
  } = await loadCapabilities()
  let now = 5_000
  const jwt = createJwtCapabilityCallback(async () => true, { now: () => now })

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
