import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

async function routePolicy() {
  return import('../src/lib/routeAccess.ts')
}

test('regular sessions are redirected away from staff-only catalog routes', async () => {
  const { decideRouteAccess } = await routePolicy()

  assert.deepEqual(
    decideRouteAccess('/products/new', 'authenticated', false),
    { kind: 'redirect', destination: '/products' },
  )
  assert.deepEqual(
    decideRouteAccess('/recipes/42', 'authenticated', false),
    { kind: 'redirect', destination: '/recipes' },
  )
  assert.deepEqual(
    decideRouteAccess('/servings/new', 'authenticated', false),
    { kind: 'redirect', destination: '/products' },
  )
  assert.deepEqual(
    decideRouteAccess('/products/new/', 'authenticated', false),
    { kind: 'redirect', destination: '/products' },
  )
})

test('staff sessions can access catalog create, edit, delete, and serving routes', async () => {
  const { decideRouteAccess } = await routePolicy()

  for (const pathname of [
    '/products/new',
    '/products/42',
    '/recipes/new',
    '/recipes/42',
    '/servings/new',
    '/servings/42',
  ]) {
    assert.deepEqual(
      decideRouteAccess(pathname, 'authenticated', true),
      { kind: 'allow' },
    )
  }
})

test('unauthenticated and expired protected sessions gate deep links at sign-in', async () => {
  const { decideRouteAccess } = await routePolicy()

  assert.deepEqual(
    decideRouteAccess('/plans/new', 'unauthenticated', false),
    {
      kind: 'redirect',
      destination: '/login?callbackUrl=%2Fplans%2Fnew',
    },
  )
  assert.deepEqual(decideRouteAccess('/plans/new', 'loading', false), {
    kind: 'loading',
  })
})

test('login and public landing routes remain available without a session', async () => {
  const { decideRouteAccess } = await routePolicy()

  assert.deepEqual(decideRouteAccess('/login', 'unauthenticated', false), {
    kind: 'allow',
  })
  assert.deepEqual(decideRouteAccess('/login/', 'unauthenticated', false), {
    kind: 'allow',
  })
  assert.deepEqual(decideRouteAccess('/', 'unauthenticated', false), {
    kind: 'allow',
  })
})

test('authenticated sessions leave the login route instead of rendering a login loop', async () => {
  const { decideRouteAccess } = await routePolicy()

  assert.deepEqual(decideRouteAccess('/login', 'authenticated', false), {
    kind: 'redirect',
    destination: '/',
  })
  assert.deepEqual(decideRouteAccess('/login/', 'authenticated', true), {
    kind: 'redirect',
    destination: '/',
  })
})

test('login callback destinations preserve local deep links and reject external redirects', async () => {
  const { safeCallbackPath } = await routePolicy()

  assert.equal(safeCallbackPath('/plans/new'), '/plans/new')
  assert.equal(safeCallbackPath('/recipes/42?tab=summary'), '/recipes/42?tab=summary')
  assert.equal(safeCallbackPath('//example.com/escape'), '/')
  assert.equal(safeCallbackPath('https://example.com/escape'), '/')
  assert.equal(safeCallbackPath('/\\example.com/escape'), '/')
  assert.equal(safeCallbackPath('/login'), '/')
  assert.equal(safeCallbackPath('/login?callbackUrl=%2Flogin'), '/')
  assert.equal(safeCallbackPath(null), '/')

  const source = await readFile(
    new URL('../src/app/login/page.tsx', import.meta.url),
    'utf8',
  )
  assert.match(source, /safeCallbackPath\(searchParams\.get\('callbackUrl'\)\)/)
  assert.match(source, /router\.push\(callbackPath\)/)
})

test('AppShell applies route policy before rendering protected children', async () => {
  const source = await readFile(
    new URL('../src/components/AppShell.tsx', import.meta.url),
    'utf8',
  )

  assert.match(source, /usePathname\(\)/)
  assert.match(source, /decideRouteAccess\(pathname, status, session\?\.user\?\.isStaff/)
  assert.match(source, /router\.replace\(access\.destination\)/)
  assert.match(source, /data-testid="auth-redirecting"/)
  assert.ok(
    source.indexOf("access.kind === 'redirect'") < source.indexOf('<Sidebar />'),
    'protected children can render before redirect gating',
  )
})
