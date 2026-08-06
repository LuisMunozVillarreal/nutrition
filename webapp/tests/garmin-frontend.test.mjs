import assert from 'node:assert/strict'
import { afterEach, beforeAll, beforeEach, test, vi } from 'vitest'
import { JSDOM } from 'jsdom'
import React from 'react'

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://example.com/',
})
const NativeURL = globalThis.URL
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  HTMLElement: dom.window.HTMLElement,
  Node: dom.window.Node,
  Event: dom.window.Event,
  MouseEvent: dom.window.MouseEvent,
  getComputedStyle: dom.window.getComputedStyle,
  IS_REACT_ACT_ENVIRONMENT: true,
  URL: class TestURL extends NativeURL {
    constructor(url, base) {
      super(url, base ?? 'http://example.com/')
    }
  },
})

globalThis.requestAnimationFrame = (callback) =>
  setTimeout(() => callback(Date.now()), 0)
globalThis.cancelAnimationFrame = (handle) => clearTimeout(handle)
Object.defineProperty(document, 'hidden', { configurable: true, value: false })
dom.window.matchMedia = (query) => ({
  matches: false,
  media: query,
  listeners: [],
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
})

const rtl = await import('@testing-library/react')
const { cleanup, fireEvent, render, screen, waitFor } = rtl.default ?? rtl

const state = {
  request: vi.fn(),
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  confirm: vi.fn(),
}

dom.window.confirm = state.confirm
globalThis.fetch = async (...args) => {
  const data = await state.request(...args)
  return new Response(JSON.stringify({ data }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

vi.doMock('next/navigation', () => ({
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({
    push: state.push,
    replace: state.replace,
    refresh: state.refresh,
  }),
}))
vi.doMock('@/lib/graphql', () => ({
  gql: (parts, ...values) => String.raw({ raw: parts }, ...values),
  graphqlRequest: (...args) => state.request(...args),
}))

let GarminConnect
let SettingsPage
let GarminCallbackPage
let garminCallback
let handoff

beforeAll(async () => {
  ;({ default: GarminConnect } = await import(
    '../src/components/GarminConnect.tsx'
  ))
  ;({ default: SettingsPage } = await import('../src/app/settings/page.tsx'))
  ;({ default: GarminCallbackPage } = await import(
    '../src/app/settings/garmin-callback/page.tsx'
  ))
  garminCallback = await import('../src/lib/garminCallback.ts')
  handoff = await import('../src/lib/garminCallbackHandoff.ts')
})

beforeEach(() => {
  state.request.mockReset()
  state.push.mockReset()
  state.replace.mockReset()
  state.refresh.mockReset()
  state.confirm.mockReset()
  dom.window.sessionStorage.clear()
})

afterEach(() => {
  cleanup()
})

const STATUS = {
  enabled: true,
  connected: false,
  hasRefreshToken: false,
  lastSyncedAt: null,
  lastSyncSummary: null,
}

function renderConnect(props = {}) {
  return render(
    React.createElement(GarminConnect, {
      status: STATUS,
      loading: false,
      requestError: null,
      onStatusRefresh: () => undefined,
      ...props,
    }),
  )
}

function paramsOf(entries) {
  return {
    getAll(name) {
      return entries[name] ?? []
    },
  }
}

function storingHistory() {
  return {
    state: null,
    replaceState() {
      return undefined
    },
  }
}

test('garminCallback maps access_denied and generic provider errors', () => {
  assert.equal(
    garminCallback.garminProviderErrorMessage('access_denied'),
    'Garmin sign-in was cancelled.',
  )
  assert.equal(
    garminCallback.garminProviderErrorMessage('other'),
    'Garmin sign-in failed. Please try again.',
  )
})

test('garminCallback accepts success and providerError params', () => {
  assert.deepEqual(
    garminCallback.parseGarminCallbackParams(
      paramsOf({ code: ['c1'], state: ['s1'] }),
    ),
    { kind: 'success', code: 'c1', state: 's1' },
  )
  assert.deepEqual(
    garminCallback.parseGarminCallbackParams(
      paramsOf({ error: ['access_denied'], state: ['s1'] }),
    ),
    { kind: 'providerError', error: 'access_denied', state: 's1' },
  )
})

test('garminCallback rejects malformed or conflicting params', () => {
  const invalid = (entries) =>
    assert.equal(
      garminCallback.parseGarminCallbackParams(paramsOf(entries)).kind,
      'invalid',
    )
  invalid({})
  invalid({ code: ['c1'] })
  invalid({ state: ['s1'] })
  invalid({ code: ['c1', 'c2'], state: ['s1'] })
  invalid({ code: ['c1'], state: ['s1'], error_description: ['oops'] })
  invalid({ code: ['  '], state: ['s1'] })
  invalid({ error: ['denied'], state: ['s1'], code: ['c1'] })
  invalid({ error: ['denied'], state: ['s1'], error_description: ['a', 'b'] })
  invalid({ error: ['denied'] })
})

test('captureGarminCallbackHandoff ignores unrelated routes and clean URLs', () => {
  assert.equal(
    handoff.captureGarminCallbackHandoff(
      '/settings',
      paramsOf({ code: ['c1'] }),
      dom.window.sessionStorage,
      storingHistory(),
    ),
    false,
  )
  assert.equal(
    handoff.captureGarminCallbackHandoff(
      handoff.GARMIN_CALLBACK_PATH,
      paramsOf({}),
      dom.window.sessionStorage,
      storingHistory(),
    ),
    false,
  )
})

test('captureGarminCallbackHandoff stores success and provider errors', () => {
  const now = 1_700_000_000_000
  assert.equal(
    handoff.captureGarminCallbackHandoff(
      handoff.GARMIN_CALLBACK_PATH,
      paramsOf({ code: ['c1'], state: ['s1'] }),
      dom.window.sessionStorage,
      storingHistory(),
      now,
    ),
    true,
  )
  assert.deepEqual(
    handoff.consumeGarminCallbackHandoff(dom.window.sessionStorage, now),
    { kind: 'success', code: 'c1', state: 's1' },
  )

  assert.equal(
    handoff.captureGarminCallbackHandoff(
      handoff.GARMIN_CALLBACK_PATH,
      paramsOf({ error: ['access_denied'], state: ['s1'] }),
      dom.window.sessionStorage,
      storingHistory(),
      now,
    ),
    true,
  )
  assert.deepEqual(
    handoff.consumeGarminCallbackHandoff(dom.window.sessionStorage, now),
    { kind: 'providerError', error: 'access_denied', state: 's1' },
  )
})

test('captureGarminCallbackHandoff scrubs URL and skips invalid payloads', () => {
  const replaced = { called: false }
  const history = {
    state: null,
    replaceState(_state, _unused, url) {
      replaced.called = true
      assert.equal(url, handoff.GARMIN_CALLBACK_PATH)
    },
  }
  assert.equal(
    handoff.captureGarminCallbackHandoff(
      handoff.GARMIN_CALLBACK_PATH,
      paramsOf({ code: ['c1'] }),
      dom.window.sessionStorage,
      history,
    ),
    true,
  )
  assert.equal(replaced.called, true)
  // Invalid callback results clear the handoff and store nothing.
  assert.equal(
    handoff.captureGarminCallbackHandoff(
      handoff.GARMIN_CALLBACK_PATH,
      paramsOf({ code: ['c1', 'c2'], state: ['s1'] }),
      dom.window.sessionStorage,
      storingHistory(),
    ),
    true,
  )
  assert.equal(
    handoff.consumeGarminCallbackHandoff(dom.window.sessionStorage).kind,
    'invalid',
  )
  // Non-safe-integer timestamps are not stored.
  assert.equal(
    handoff.captureGarminCallbackHandoff(
      handoff.GARMIN_CALLBACK_PATH,
      paramsOf({ code: ['c1'], state: ['s1'] }),
      dom.window.sessionStorage,
      storingHistory(),
      Number.NaN,
    ),
    true,
  )
  assert.equal(
    handoff.consumeGarminCallbackHandoff(dom.window.sessionStorage).kind,
    'invalid',
  )
})

test('captureGarminCallbackHandoff fails closed when history or storage throws', () => {
  const throwingHistory = {
    state: null,
    replaceState() {
      throw new Error('history blocked')
    },
  }
  assert.equal(
    handoff.captureGarminCallbackHandoff(
      handoff.GARMIN_CALLBACK_PATH,
      paramsOf({ code: ['c1'], state: ['s1'] }),
      dom.window.sessionStorage,
      throwingHistory,
    ),
    false,
  )

  const throwingStorage = {
    getItem() {
      return null
    },
    setItem() {
      throw new Error('quota')
    },
    removeItem() {
      return undefined
    },
  }
  assert.equal(
    handoff.captureGarminCallbackHandoff(
      handoff.GARMIN_CALLBACK_PATH,
      paramsOf({ code: ['c1'], state: ['s1'] }),
      throwingStorage,
      storingHistory(),
    ),
    true,
  )
})

test('consumeGarminCallbackHandoff rejects missing, oversized, malformed, and expired values', () => {
  const now = 1_700_000_000_000
  const missing = {
    getItem() {
      return null
    },
    setItem() {
      return undefined
    },
    removeItem() {
      return undefined
    },
  }
  assert.equal(handoff.consumeGarminCallbackHandoff(missing, now).kind, 'invalid')

  const oversized = {
    getItem() {
      return 'x'.repeat(handoff.GARMIN_CALLBACK_HANDOFF_MAX_AGE_MS * 100)
    },
    setItem() {
      return undefined
    },
    removeItem() {
      return undefined
    },
  }
  assert.equal(
    handoff.consumeGarminCallbackHandoff(oversized, now).kind,
    'invalid',
  )

  const throwingGet = {
    getItem() {
      throw new Error('storage blocked')
    },
    setItem() {
      return undefined
    },
    removeItem() {
      return undefined
    },
  }
  assert.equal(
    handoff.consumeGarminCallbackHandoff(throwingGet, now).kind,
    'invalid',
  )

  const failingClear = {
    getItem() {
      return '{"version":1,"capturedAt":1,"result":{"kind":"success","code":"c","state":"s"}}'
    },
    setItem() {
      return undefined
    },
    removeItem() {
      throw new Error('clear blocked')
    },
  }
  assert.equal(
    handoff.consumeGarminCallbackHandoff(failingClear, now).kind,
    'invalid',
  )

  const unparsable = {
    getItem() {
      return '{not json'
    },
    setItem() {
      return undefined
    },
    removeItem() {
      return undefined
    },
  }
  assert.equal(
    handoff.consumeGarminCallbackHandoff(unparsable, now).kind,
    'invalid',
  )

  const wrongShape = {
    getItem() {
      return JSON.stringify({
        version: 1,
        capturedAt: now,
        result: { kind: 'bogus' },
      })
    },
    setItem() {
      return undefined
    },
    removeItem() {
      return undefined
    },
  }
  assert.equal(
    handoff.consumeGarminCallbackHandoff(wrongShape, now).kind,
    'invalid',
  )

  const expired = {
    getItem() {
      return JSON.stringify({
        version: 1,
        capturedAt: now - handoff.GARMIN_CALLBACK_HANDOFF_MAX_AGE_MS - 1,
        result: { kind: 'success', code: 'c', state: 's' },
      })
    },
    setItem() {
      return undefined
    },
    removeItem() {
      return undefined
    },
  }
  assert.equal(
    handoff.consumeGarminCallbackHandoff(expired, now).kind,
    'invalid',
  )

  const futureDated = {
    getItem() {
      return JSON.stringify({
        version: 1,
        capturedAt: now + 60_000,
        result: { kind: 'success', code: 'c', state: 's' },
      })
    },
    setItem() {
      return undefined
    },
    removeItem() {
      return undefined
    },
  }
  assert.equal(
    handoff.consumeGarminCallbackHandoff(futureDated, now).kind,
    'invalid',
  )

  assert.equal(
    handoff.consumeGarminCallbackHandoff(missing, Number.NaN).kind,
    'invalid',
  )
})

test('consumeGarminCallbackHandoff rejects structurally incomplete results', () => {
  const now = 1_700_000_000_000
  const withResult = (result) => ({
    getItem() {
      return JSON.stringify({ version: 1, capturedAt: now, result })
    },
    setItem() {
      return undefined
    },
    removeItem() {
      return undefined
    },
  })
  assert.equal(
    handoff.consumeGarminCallbackHandoff(
      withResult({ kind: 'success', code: '', state: 's' }),
      now,
    ).kind,
    'invalid',
  )
  assert.equal(
    handoff.consumeGarminCallbackHandoff(
      withResult({ kind: 'success', code: 'c', state: '' }),
      now,
    ).kind,
    'invalid',
  )
  assert.equal(
    handoff.consumeGarminCallbackHandoff(
      withResult({ kind: 'success', code: 5, state: 's' }),
      now,
    ).kind,
    'invalid',
  )
  assert.equal(
    handoff.consumeGarminCallbackHandoff(
      withResult({ kind: 'providerError', error: '', state: 's' }),
      now,
    ).kind,
    'invalid',
  )
  assert.equal(
    handoff.consumeGarminCallbackHandoff(
      withResult({ kind: 'providerError', error: 'e', state: ' ' }),
      now,
    ).kind,
    'invalid',
  )
  assert.equal(
    handoff.consumeGarminCallbackHandoff(withResult(null), now).kind,
    'invalid',
  )

  const nonObjectHandoff = {
    getItem() {
      return 'null'
    },
    setItem() {
      return undefined
    },
    removeItem() {
      return undefined
    },
  }
  assert.equal(
    handoff.consumeGarminCallbackHandoff(nonObjectHandoff, now).kind,
    'invalid',
  )
})

test('captureGarminCallbackHandoff tolerates storage clearing failures', () => {
  const storage = {
    getItem() {
      return null
    },
    setItem() {
      return undefined
    },
    removeItem() {
      throw new Error('clear blocked')
    },
  }
  assert.equal(
    handoff.captureGarminCallbackHandoff(
      handoff.GARMIN_CALLBACK_PATH,
      paramsOf({ code: ['c1'], state: ['s1'] }),
      storage,
      storingHistory(),
    ),
    true,
  )
})

test('GarminConnect renders loading and unknown states without actions', () => {
  renderConnect({ loading: true })
  assert.ok(screen.getByTestId('garmin-loading'))

  cleanup()
  renderConnect({ status: null })
  assert.equal(screen.getByTestId('garmin-status').textContent, 'Status: Unknown')
  assert.equal(screen.getByTestId('garmin-enabled').textContent, 'Unavailable')
  assert.equal(screen.getByTestId('garmin-connected').textContent, 'No')
  assert.equal(screen.queryByTestId('garmin-connect-btn'), null)
  assert.equal(screen.queryByTestId('garmin-disconnect-btn'), null)
})

test('GarminConnect shows disabled and disconnected states', () => {
  renderConnect({ status: { ...STATUS, enabled: false } })
  assert.equal(screen.getByTestId('garmin-status').textContent, 'Status: Disabled')
  assert.equal(screen.queryByTestId('garmin-connect-btn'), null)

  cleanup()
  renderConnect()
  assert.equal(screen.getByTestId('garmin-status').textContent, 'Status: Disconnected')
  assert.ok(screen.getByTestId('garmin-connect-btn'))
  assert.equal(screen.queryByTestId('garmin-disconnect-btn'), null)
  assert.equal(screen.getByTestId('garmin-last-sync').textContent, 'Never')
})

test('GarminConnect starts authorization and forwards to the provider', async () => {
  renderConnect()
  state.request.mockResolvedValueOnce({
    beginGarminAuthorization: {
      authorizationUrl: '#oauth-start',
      state: 's1',
      expiresAt: '2026-08-06T00:00:00Z',
    },
  })

  fireEvent.click(screen.getByTestId('garmin-connect-btn'))
  await waitFor(() => assert.equal(window.location.hash, '#oauth-start'))
})

test('GarminConnect surfaces connect failures with fallback text', async () => {
  renderConnect()
  state.request.mockRejectedValueOnce(new Error('boom'))
  fireEvent.click(screen.getByTestId('garmin-connect-btn'))
  await waitFor(() => assert.equal(screen.getByTestId('garmin-error').textContent, 'boom'))

  cleanup()
  renderConnect()
  state.request.mockRejectedValueOnce('not an error')
  fireEvent.click(screen.getByTestId('garmin-connect-btn'))
  await waitFor(() =>
    assert.equal(
      screen.getByTestId('garmin-error').textContent,
      'Garmin request failed. Please try again.',
    ),
  )

  cleanup()
  renderConnect()
  state.request.mockRejectedValueOnce(new Error(''))
  fireEvent.click(screen.getByTestId('garmin-connect-btn'))
  await waitFor(() =>
    assert.equal(
      screen.getByTestId('garmin-error').textContent,
      'Garmin request failed. Please try again.',
    ),
  )
})

test('GarminConnect disconnects after confirmation and refreshes status', async () => {
  state.confirm.mockReturnValueOnce(true)
  state.request.mockResolvedValueOnce({ disconnectGarmin: true })
  const refreshed = vi.fn()
  renderConnect({
    status: { ...STATUS, connected: true },
    onStatusRefresh: refreshed,
  })
  fireEvent.click(screen.getByTestId('garmin-disconnect-btn'))
  await waitFor(() => assert.equal(refreshed.mock.calls.length, 1))
  assert.equal(state.confirm.mock.calls.length, 1)
})

test('GarminConnect skips disconnect when declined or already disconnected', async () => {
  renderConnect({ status: { ...STATUS, connected: true } })
  state.confirm.mockReturnValueOnce(false)
  fireEvent.click(screen.getByTestId('garmin-disconnect-btn'))
  await waitFor(() => assert.equal(state.request.mock.calls.length, 0))

  state.confirm.mockReturnValueOnce(true)
  state.request.mockResolvedValueOnce({ disconnectGarmin: false })
  fireEvent.click(screen.getByTestId('garmin-disconnect-btn'))
  await waitFor(() =>
    assert.equal(
      screen.getByTestId('garmin-error').textContent,
      'Garmin was already disconnected.',
    ),
  )
})

test('GarminConnect surfaces disconnect failures', async () => {
  renderConnect({ status: { ...STATUS, connected: true } })
  state.confirm.mockReturnValueOnce(true)
  state.request.mockRejectedValueOnce(new Error('disconnect boom'))
  fireEvent.click(screen.getByTestId('garmin-disconnect-btn'))
  await waitFor(() =>
    assert.equal(
      screen.getByTestId('garmin-error').textContent,
      'disconnect boom',
    ),
  )
})

test('GarminConnect shows cached refresh token, sync summary, and request error', () => {
  renderConnect({
    status: {
      ...STATUS,
      connected: true,
      hasRefreshToken: true,
      lastSyncedAt: '2026-08-05T12:00:00.000Z',
      lastSyncSummary: {
        imported: 4,
        duplicates: 1,
        unsupported: 2,
        invalid: 0,
      },
    },
    requestError: 'backend unavailable',
  })
  assert.equal(screen.getByTestId('garmin-refresh').textContent, 'Stored')
  assert.match(
    screen.getByTestId('garmin-last-sync').textContent,
    /8\/5\/2026|05\/08\/2026|Aug 5, 2026|5 Aug 2026|2026/,
  )
  assert.match(
    screen.getByTestId('garmin-sync-summary').textContent,
    /4 imported, 1 duplicates, 2 unsupported, 0 invalid/,
  )
  assert.equal(screen.getByTestId('garmin-error').textContent, 'backend unavailable')
})

test('Settings page loads status and shows errors', async () => {
  state.request.mockResolvedValueOnce({ garminStatus: STATUS })
  render(React.createElement(SettingsPage))
  await waitFor(() =>
    assert.ok(screen.getByTestId('garmin-card')),
  )
  assert.equal(screen.getByTestId('settings-title').textContent, 'Settings')
  assert.equal(screen.getByTestId('garmin-connected').textContent, 'No')

  cleanup()
  state.request.mockRejectedValueOnce(new Error('settings boom'))
  render(React.createElement(SettingsPage))
  await waitFor(() =>
    assert.equal(screen.getByTestId('garmin-error').textContent, 'settings boom'),
  )

  cleanup()
  state.request.mockRejectedValueOnce('opaque failure')
  render(React.createElement(SettingsPage))
  await waitFor(() =>
    assert.equal(
      screen.getByTestId('garmin-error').textContent,
      'Unable to load Garmin integration status.',
    ),
  )
})

test('Garmin callback page completes authorization and returns to settings', async () => {
  const now = Date.now()
  handoff.captureGarminCallbackHandoff(
    handoff.GARMIN_CALLBACK_PATH,
    paramsOf({ code: ['c1'], state: ['s1'] }),
    dom.window.sessionStorage,
    storingHistory(),
    now,
  )
  state.request.mockResolvedValueOnce({ completeGarminAuthorization: STATUS })

  render(React.createElement(GarminCallbackPage))
  await waitFor(() =>
    assert.ok(screen.getByTestId('garmin-callback-success')),
  )
  assert.equal(state.replace.mock.calls.length, 1)
  assert.equal(state.replace.mock.calls[0][0], '/settings')
})

test('Garmin callback page reports completion failures', async () => {
  const now = Date.now()
  handoff.captureGarminCallbackHandoff(
    handoff.GARMIN_CALLBACK_PATH,
    paramsOf({ code: ['c1'], state: ['s1'] }),
    dom.window.sessionStorage,
    storingHistory(),
    now,
  )
  state.request.mockRejectedValueOnce(new Error('exchange failed'))

  render(React.createElement(GarminCallbackPage))
  await waitFor(() =>
    assert.equal(
      screen.getByTestId('garmin-callback-error').textContent,
      'Garmin connection failed during completion.',
    ),
  )
})

test('Garmin callback page cancels provider errors and returns to settings', async () => {
  const now = Date.now()
  handoff.captureGarminCallbackHandoff(
    handoff.GARMIN_CALLBACK_PATH,
    paramsOf({ error: ['access_denied'], state: ['s1'] }),
    dom.window.sessionStorage,
    storingHistory(),
    now,
  )
  state.request.mockResolvedValueOnce({ cancelGarminAuthorization: true })

  render(React.createElement(GarminCallbackPage))
  await waitFor(() =>
    assert.equal(
      screen.getByTestId('garmin-callback-error').textContent,
      'Garmin sign-in was cancelled.',
    ),
  )
})

test('Garmin callback page handles cancel failures and generic provider errors', async () => {
  const now = Date.now()
  handoff.captureGarminCallbackHandoff(
    handoff.GARMIN_CALLBACK_PATH,
    paramsOf({ error: ['server_error'], state: ['s1'] }),
    dom.window.sessionStorage,
    storingHistory(),
    now,
  )
  state.request.mockRejectedValueOnce(new Error('cancel failed'))

  render(React.createElement(GarminCallbackPage))
  await waitFor(() =>
    assert.equal(
      screen.getByTestId('garmin-callback-error').textContent,
      'Garmin sign-in failed. Please try again.',
    ),
  )
  fireEvent.click(screen.getByTestId('garmin-callback-return'))
  assert.equal(state.replace.mock.calls[0][0], '/settings')
})

test('Garmin callback page explains missing or expired handoffs', async () => {
  render(React.createElement(GarminCallbackPage))
  await waitFor(() =>
    assert.match(
      screen.getByTestId('garmin-callback-error').textContent,
      /Start the connection again/,
    ),
  )
})
