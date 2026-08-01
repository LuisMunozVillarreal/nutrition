import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { buildSchema, parse, validate } from 'graphql'

async function readOperation(path, constantName) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8')
  const match = source.match(
    new RegExp(`const ${constantName} = gql\`([\\s\\S]*?)\``),
  )
  assert.ok(match, `${constantName} not found in ${path}`)
  return match[1]
}

const garminSchema = buildSchema(`
  type GarminSyncSummaryType {
    imported: Int!
    duplicates: Int!
    unsupported: Int!
    invalid: Int!
  }

  type GarminAuthStart {
    authorizationUrl: String!
    state: String!
    expiresAt: String!
  }

  type GarminStatus {
    enabled: Boolean!
    connected: Boolean!
    hasRefreshToken: Boolean!
    lastSyncedAt: String
    lastSyncSummary: GarminSyncSummaryType
  }

  type Query {
    garminStatus: GarminStatus
  }

  type Mutation {
    beginGarminAuthorization: GarminAuthStart!
    cancelGarminAuthorization(state: String!): Boolean!
    completeGarminAuthorization(code: String!, state: String!): GarminStatus!
    disconnectGarmin: Boolean!
  }

  schema {
    query: Query
    mutation: Mutation
  }
`)

test('Garmin callback parser validates state-bound provider errors and safe messages', async () => {
  const {
    garminProviderErrorMessage,
    parseGarminCallbackParams,
  } = await import('../src/lib/garminCallback.ts')

  assert.deepEqual(
    parseGarminCallbackParams(new URLSearchParams('code=abc123&state=state-1')),
    { kind: 'success', code: 'abc123', state: 'state-1' },
  )

  assert.deepEqual(
    parseGarminCallbackParams(
      new URLSearchParams(
        'error=access_denied&error_description=User%20cancelled&state=state-2',
      ),
    ),
    {
      kind: 'providerError',
      error: 'access_denied',
      state: 'state-2',
    },
  )

  assert.equal(
    garminProviderErrorMessage('access_denied'),
    'Garmin sign-in was cancelled.',
  )
  assert.equal(
    garminProviderErrorMessage('provider_internal_failure'),
    'Garmin sign-in failed. Please try again.',
  )
  assert.equal(
    garminProviderErrorMessage('<script>untrusted provider text</script>'),
    'Garmin sign-in failed. Please try again.',
  )

  for (const query of [
    'error=access_denied',
    'error=access_denied&state=',
    'error=access_denied&state=one&state=two',
    'error=access_denied&state=one&code=unexpected',
  ]) {
    assert.equal(
      parseGarminCallbackParams(new URLSearchParams(query)).kind,
      'invalid',
    )
  }

  assert.deepEqual(
    parseGarminCallbackParams(new URLSearchParams('code=a&code=b&state=single')),
    {
      kind: 'invalid',
      message:
        'Expected exactly one Garmin OAuth code and state parameter on callback.',
    },
  )
})

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial))
  return {
    getItem(key) {
      return values.get(key) ?? null
    },
    setItem(key, value) {
      values.set(key, value)
    },
    removeItem(key) {
      values.delete(key)
    },
  }
}

test('Garmin callback handoff scrubs OAuth values and resumes exactly once', async () => {
  const {
    captureGarminCallbackHandoff,
    consumeGarminCallbackHandoff,
  } = await import('../src/lib/garminCallbackHandoff.ts')
  const storage = memoryStorage()
  const history = {
    state: { navigation: 'preserved' },
    url: '/settings/garmin-callback?code=one-time-code&state=one-time-state',
    replaceState(state, _unused, url) {
      this.state = state
      this.url = url
    },
  }

  assert.equal(
    captureGarminCallbackHandoff(
      '/settings/garmin-callback',
      new URLSearchParams('code=one-time-code&state=one-time-state'),
      storage,
      history,
      1_000,
    ),
    true,
  )
  assert.equal(history.url, '/settings/garmin-callback')
  assert.doesNotMatch(history.url, /one-time-(?:code|state)/)
  assert.deepEqual(consumeGarminCallbackHandoff(storage, 1_001), {
    kind: 'success',
    code: 'one-time-code',
    state: 'one-time-state',
  })
  assert.equal(consumeGarminCallbackHandoff(storage, 1_002).kind, 'invalid')
})

test('Garmin callback handoff scrubs state-bound provider errors exactly once', async () => {
  const {
    GARMIN_CALLBACK_HANDOFF_MAX_AGE_MS,
    captureGarminCallbackHandoff,
    consumeGarminCallbackHandoff,
  } = await import('../src/lib/garminCallbackHandoff.ts')
  const storage = memoryStorage()
  const history = {
    state: null,
    url: '/settings/garmin-callback?error=access_denied&error_description=cancelled&state=provider-error-state',
    replaceState(state, _unused, url) {
      this.state = state
      this.url = url
    },
  }

  captureGarminCallbackHandoff(
    '/settings/garmin-callback',
    new URLSearchParams(
      'error=access_denied&error_description=cancelled&state=provider-error-state',
    ),
    storage,
    history,
    5_000,
  )
  assert.equal(history.url, '/settings/garmin-callback')
  assert.deepEqual(consumeGarminCallbackHandoff(storage, 5_001), {
    kind: 'providerError',
    error: 'access_denied',
    state: 'provider-error-state',
  })
  assert.equal(consumeGarminCallbackHandoff(storage, 5_002).kind, 'invalid')

  captureGarminCallbackHandoff(
    '/settings/garmin-callback',
    new URLSearchParams('code=expired-code&state=expired-state'),
    storage,
    history,
    10_000,
  )
  assert.equal(
    consumeGarminCallbackHandoff(
      storage,
      10_000 + GARMIN_CALLBACK_HANDOFF_MAX_AGE_MS + 1,
    ).kind,
    'invalid',
  )

  storage.setItem('nutrition.garmin.callback-handoff.v1', '{malformed')
  assert.equal(consumeGarminCallbackHandoff(storage, 20_000).kind, 'invalid')
})

test('Garmin callback flow uses only tab-local handoff storage', async () => {
  const handoffSource = await readFile(
    new URL('../src/lib/garminCallbackHandoff.ts', import.meta.url),
    'utf8',
  )
  const callbackSource = await readFile(
    new URL('../src/app/settings/garmin-callback/page.tsx', import.meta.url),
    'utf8',
  )

  assert.doesNotMatch(handoffSource, /localStorage|document\.cookie|console\./)
  assert.match(callbackSource, /consumeGarminCallbackHandoff\(window\.sessionStorage\)/)
  assert.doesNotMatch(callbackSource, /parseGarminCallbackParams\(searchParams\)/)
  assert.match(callbackSource, /if \(parsed\.kind === 'providerError'\)/)
  assert.match(
    callbackSource,
    /await graphqlRequest\(CANCEL_GARMIN_AUTHORIZATION_MUTATION, \{[\s\S]*state: parsed\.state/,
  )
  assert.match(
    callbackSource,
    /setError\(garminProviderErrorMessage\(parsed\.error\)\)/,
  )
  assert.ok(
    callbackSource.indexOf(
      'await graphqlRequest(CANCEL_GARMIN_AUTHORIZATION_MUTATION',
    ) < callbackSource.indexOf(
      'setError(garminProviderErrorMessage(parsed.error))',
    ),
    'provider-safe errors must render only after cancellation is attempted',
  )
  assert.doesNotMatch(callbackSource, /errorDescription|error_description|console\./)
})

test('Garmin GraphQL documents match backend schema contracts', async () => {
  const statusQuery = await readOperation(
    '../src/app/settings/page.tsx',
    'GARMIN_STATUS_QUERY',
  )
  const beginMutation = await readOperation(
    '../src/components/GarminConnect.tsx',
    'BEGIN_GARMIN_AUTHORIZATION_MUTATION',
  )
  const completeMutation = await readOperation(
    '../src/app/settings/garmin-callback/page.tsx',
    'COMPLETE_GARMIN_AUTHORIZATION_MUTATION',
  )
  const cancelMutation = await readOperation(
    '../src/app/settings/garmin-callback/page.tsx',
    'CANCEL_GARMIN_AUTHORIZATION_MUTATION',
  )
  const disconnectMutation = await readOperation(
    '../src/components/GarminConnect.tsx',
    'DISCONNECT_GARMIN_MUTATION',
  )
  assert.equal(beginMutation.includes('beginGarminAuthorization'), true)
  assert.equal(completeMutation.includes('completeGarminAuthorization'), true)
  assert.equal(cancelMutation.includes('cancelGarminAuthorization'), true)
  assert.equal(disconnectMutation.includes('disconnectGarmin'), true)

  const beginValidation = validate(garminSchema, parse(beginMutation))
  const completeValidation = validate(garminSchema, parse(completeMutation))
  const cancelValidation = validate(garminSchema, parse(cancelMutation))
  const disconnectValidation = validate(
    garminSchema,
    parse(disconnectMutation),
  )
  assert.deepEqual(beginValidation.map((error) => error.message), [])
  assert.deepEqual(completeValidation.map((error) => error.message), [])
  assert.deepEqual(cancelValidation.map((error) => error.message), [])
  assert.deepEqual(disconnectValidation.map((error) => error.message), [])

  assert.match(statusQuery, /query GarminSettingsStatusQuery/)
  assert.match(statusQuery, /garminStatus\s*{/)
  assert.match(statusQuery, /hasRefreshToken/)
  assert.match(statusQuery, /lastSyncSummary\s*{/)
})

test('Garmin frontend files avoid direct endpoint/token plumbing', async () => {
  const source = await readFile(
    new URL('../src/components/GarminConnect.tsx', import.meta.url),
    'utf8',
  )

  assert.ok(source.includes('graphqlRequest'))
  assert.match(source, /import \{ graphqlRequest, gql \} from ['"]@\/lib\/graphql['"]/)
  assert.doesNotMatch(source, /from ['"]graphql-request['"]/)
  assert.doesNotMatch(source, /BEGIN_GARMIN_AUTHORIZATION_MUTATION.*GRAPHQL/)
  assert.doesNotMatch(source, /accessToken/)
  assert.doesNotMatch(source, /authorizationUrl\s*:\s*['"].*http/)
})

test('Garmin status UI supports disconnect while disabled if credentials are cached', async () => {
  const source = await readFile(
    new URL('../src/components/GarminConnect.tsx', import.meta.url),
    'utf8',
  )

  assert.ok(
    source.includes('const canDisconnect = status?.connected || status?.hasRefreshToken'),
    'GarminConnect should expose disconnect for cached credentials',
  )
  assert.ok(
    source.includes('const canConnect ='),
    'GarminConnect should gate connect on enabled status only',
  )
  assert.ok(
    source.includes('status?.enabled'),
    'GarminConnect connect condition should honor feature flag',
  )
  assert.ok(
    source.includes('role="status"'),
    'GarminConnect should expose loading/error states to assistive tech',
  )
  assert.ok(
    source.includes('data-testid="garmin-action-status"'),
    'GarminConnect should expose action status text for loading feedback',
  )
  assert.ok(
    source.includes('aria-busy={requestInFlight}'),
    'Garmin action controls should surface busy state accessibly',
  )
})

test('Garmin Cypress exercises the deployed bearer GraphQL lifecycle without schema mocks', async () => {
  const source = await readFile(
    new URL('../cypress/support/step_definitions/garmin.ts', import.meta.url),
    'utf8',
  )

  assert.ok(source.includes('function getGraphQLEndpoint'), 'Expected dynamic endpoint helper')
  assert.ok(
    source.includes('return new URL(endpoint, `${baseUrl}/`).href'),
    'Garmin Cypress requests should resolve GraphQL endpoint from Cypress config',
  )
  assert.doesNotMatch(source, /req\.reply\(/)
  assert.doesNotMatch(source, /GarminStatusFixture|garminConnectedStatus/)
  assert.match(source, /operation === 'GarminSettingsStatusQuery'/)
  assert.match(source, /operation === 'DisconnectGarmin'/)
  assert.match(source, /req\.continue\(\)/)
  assert.match(source, /cy\.request\(['"]\/api\/auth\/session['"]\)/)
  assert.match(source, /Authorization['"]?: `Bearer \$\{accessToken\}`/)
  assert.match(source, /garminStateRejection/)
  assert.match(source, /errors.*state/is)
  assert.match(source, /@garminStatusAfterDisconnect/)
})

test('settings route and sidebar source contracts include Garmin item and title', async () => {
  const sidebar = await readFile(
    new URL('../src/components/Sidebar.tsx', import.meta.url),
    'utf8',
  )
  const pageSource = await readFile(
    new URL('../src/app/settings/page.tsx', import.meta.url),
    'utf8',
  )
  const callbackSource = await readFile(
    new URL('../src/app/settings/garmin-callback/page.tsx', import.meta.url),
    'utf8',
  )

  assert.match(sidebar, /label: 'Settings'/)
  assert.match(sidebar, /href: '\/settings'/)
  assert.match(pageSource, /data-testid="settings-title"/)
  assert.match(pageSource, /useCallback\(/)
  assert.match(callbackSource, /consumeGarminCallbackHandoff/)
  assert.match(callbackSource, /data-testid="garmin-callback-error"/)
})
