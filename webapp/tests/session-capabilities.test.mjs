import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

async function loadCapabilities() {
  return import('../src/lib/sessionCapabilities.ts')
}

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

test('NextAuth requests and propagates the backend staff capability', async () => {
  const route = await readFile(
    new URL('../src/app/api/auth/[...nextauth]/route.ts', import.meta.url),
    'utf8',
  )
  const declarations = await readFile(
    new URL('../types/next-auth.d.ts', import.meta.url),
    'utf8',
  )

  assert.match(route, /user\s*\{[\s\S]*?isStaff[\s\S]*?\}/)
  assert.match(route, /isStaff:\s*data\.login\.user\.isStaff/)
  assert.match(route, /applyUserCapabilitiesToToken\(token, user\)/)
  assert.match(route, /applyTokenCapabilitiesToSession\(session, token\)/)
  assert.match(declarations, /isStaff:\s*boolean/)
})
