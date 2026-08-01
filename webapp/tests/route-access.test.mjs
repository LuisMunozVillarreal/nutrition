import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'vitest'

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

test('authenticated regular sessions can access routes without a staff policy', async () => {
  const { decideRouteAccess } = await routePolicy()

  assert.deepEqual(decideRouteAccess('/plans', 'authenticated', false), {
    kind: 'allow',
  })
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

test('backend reauthentication gates rolling sessions without creating a login loop', async () => {
  const { decideRouteAccess } = await routePolicy()
  const callbackPath = '/plans/new?day=2026-07-30&view=high%20protein'

  assert.deepEqual(
    decideRouteAccess('/plans/new', 'authenticated', true, callbackPath, true),
    {
      kind: 'redirect',
      destination:
        '/login?callbackUrl=%2Fplans%2Fnew%3Fday%3D2026-07-30%26view%3Dhigh%2520protein',
    },
  )
  assert.deepEqual(
    decideRouteAccess('/login', 'authenticated', true, '/login', true),
    { kind: 'allow' },
  )
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
  const { buildCallbackPath, safeCallbackPath } = await routePolicy()

  assert.equal(
    buildCallbackPath('/recipes/42', 'tab=nutrition%2Fsummary&term=high+protein'),
    '/recipes/42?tab=nutrition%2Fsummary&term=high+protein',
  )
  assert.equal(buildCallbackPath('/recipes/42', ''), '/recipes/42')
  assert.equal(safeCallbackPath('/plans/new'), '/plans/new')
  assert.equal(safeCallbackPath('/recipes/42?tab=summary'), '/recipes/42?tab=summary')
  assert.equal(safeCallbackPath('/recipes/42#untrusted-fragment'), '/recipes/42')
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
  assert.match(source, /useSearchParams\(\)/)
  assert.match(source, /buildCallbackPath\(pathname, searchParams\.toString\(\)\)/)
  assert.match(source, /BACKEND_REAUTHENTICATION_REQUIRED/)
  assert.match(source, /decideRouteAccess\(/)
  assert.match(source, /router\.replace\(access\.destination\)/)
  assert.match(source, /data-testid="auth-redirecting"/)
  assert.ok(
    source.indexOf("access.kind === 'redirect'") < source.indexOf('<Sidebar />'),
    'protected children can render before redirect gating',
  )
})

test('AppShell owns a Suspense-safe session gate with a deterministic loading fallback', async () => {
  const source = await readFile(
    new URL('../src/components/AppShell.tsx', import.meta.url),
    'utf8',
  )

  assert.match(source, /import \{[^}]*Suspense[^}]*\} from 'react'/)
  assert.match(source, /function AppShellInner\(/)
  assert.match(source, /<Suspense fallback=\{<SessionLoading \/>\}>/)
  assert.match(source, /<AppShellInner>\{children\}<\/AppShellInner>/)
  assert.match(source, /data-testid="session-loading"/)
  assert.equal(
    source.match(/Loading session\.\.\./g)?.length,
    1,
    'the Suspense and session-loading paths must share one deterministic fallback',
  )
})
