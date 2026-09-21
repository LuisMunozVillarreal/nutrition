import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'
import React from 'react'
import { afterAll, afterEach, beforeAll, test, vi } from 'vitest'

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://example.com/',
})
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  HTMLElement: dom.window.HTMLElement,
  Node: dom.window.Node,
  Event: dom.window.Event,
  MouseEvent: dom.window.MouseEvent,
  getComputedStyle: dom.window.getComputedStyle,
  IS_REACT_ACT_ENVIRONMENT: true,
})

const state = {
  request: vi.fn(),
  confirm: vi.fn(),
  dataTableProps: null,
}
globalThis.confirm = (...args) => state.confirm(...args)

vi.doMock('@/lib/graphql', () => ({
  gql: (parts, ...values) => String.raw({ raw: parts }, ...values),
  graphqlRequest: (...args) => state.request(...args),
}))
vi.doMock('@/components/DataTable', () => ({
  default: (props) => {
    state.dataTableProps = props
    return React.createElement('div', { 'data-testid': 'data-table' })
  },
}))

const rtl = await import('@testing-library/react')
const { render, screen, fireEvent, waitFor, act, cleanup, within } = rtl.default ?? rtl

let HealthSyncPanel
let DevicesPage
let StepsPage

beforeAll(async () => {
  ;({ default: HealthSyncPanel } = await import(
    '../src/app/devices/HealthSyncPanel.tsx'
  ))
  ;({ default: DevicesPage } = await import('../src/app/devices/page.tsx'))
  ;({ default: StepsPage } = await import('../src/app/steps/page.tsx'))
})

afterEach(() => {
  cleanup()
  state.request.mockReset()
  state.confirm.mockReset()
  state.dataTableProps = null
  vi.useRealTimers()
})

afterAll(() => {
  vi.doUnmock('@/lib/graphql')
  vi.doUnmock('@/components/DataTable')
  vi.resetModules()
})

const devices = [
  {
    id: 'one',
    name: 'Current phone',
    lastSeenAt: null,
    lastSuccessAt: '2026-08-21T12:00:00Z',
    expiresAt: '2027-01-01T00:00:00Z',
    createdAt: '2026-08-01T00:00:00Z',
  },
  {
    id: 'two',
    name: 'New phone',
    lastSeenAt: null,
    lastSuccessAt: null,
    expiresAt: '2027-01-02T00:00:00Z',
    createdAt: '2026-08-02T00:00:00Z',
  },
]

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const flushPromises = () => new Promise((resolve) => setImmediate(resolve))

test('health sync panel loads devices and creates an expiring pairing code', async () => {
  const expiryCallbacks = []
  const setTimeoutSpy = vi.spyOn(window, 'setTimeout').mockImplementation((callback) => {
    expiryCallbacks.push(callback)
    return 1
  })
  const clearTimeoutSpy = vi.spyOn(window, 'clearTimeout').mockImplementation(() => {})
  const pairing = {
    code: '123456789012',
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
  }
  state.request
    .mockResolvedValueOnce({ healthSyncDevices: devices })
    .mockResolvedValueOnce({ createHealthSyncPairingCode: pairing })

  render(React.createElement(HealthSyncPanel))
  await screen.findByText('Current phone')
  assert.match(screen.getByText(/Last synced/).textContent, /Last synced/)
  const pairedStatus = screen
    .getAllByText(/^Paired /)
    .find((element) => element.tagName === 'P')
  assert.match(pairedStatus.textContent, /Paired/)

  fireEvent.click(screen.getByRole('button', { name: 'Pair Android phone' }))
  assert.equal((await screen.findByTestId('pairing-code')).textContent, pairing.code)
  assert.match(screen.getByText(/Enter this code/).textContent, /only be used once/)
  await act(async () => flushPromises())
  assert.equal(expiryCallbacks.length, 1)
  await act(async () => expiryCallbacks[0]())
  assert.equal(screen.queryByTestId('pairing-code'), null)
  assert.deepEqual(clearTimeoutSpy.mock.calls[0], [1])
  setTimeoutSpy.mockRestore()
  clearTimeoutSpy.mockRestore()
})

test('pairing is a dedicated devices destination and is absent from steps', async () => {
  state.request.mockResolvedValue({ healthSyncDevices: [] })

  const devicesView = render(React.createElement(DevicesPage))
  assert.ok(await within(devicesView.container).findByRole('heading', { name: 'Devices' }))
  assert.ok(within(devicesView.container).getByRole('button', { name: 'Pair Android phone' }))
  devicesView.unmount()

  state.request.mockResolvedValueOnce({ dayStepsList: [] })
  const stepsView = render(React.createElement(StepsPage))
  await waitFor(() => assert.equal(state.dataTableProps.loading, false))
  assert.equal(
    within(stepsView.container).queryByRole('button', { name: 'Pair Android phone' }),
    null,
  )
})

test('health sync panel exposes loading and pairing failure states', async () => {
  const pending = deferred()
  state.request
    .mockResolvedValueOnce({ healthSyncDevices: [] })
    .mockImplementationOnce(() => pending.promise)

  render(React.createElement(HealthSyncPanel))
  await screen.findByText('No Android companion is paired yet.')
  fireEvent.click(screen.getByRole('button', { name: 'Pair Android phone' }))
  assert.equal(screen.getByRole('button', { name: 'Working…' }).disabled, true)
  await act(async () => pending.reject(new Error('pair failed')))
  assert.equal(
    (await screen.findByRole('alert')).textContent,
    'Could not create a pairing code. Please try again.',
  )
})

test('health sync panel reports an initial device-load failure', async () => {
  state.request.mockRejectedValueOnce(new Error('load failed'))

  render(React.createElement(HealthSyncPanel))

  assert.equal(
    (await screen.findByRole('alert')).textContent,
    'Could not load paired health devices.',
  )
})

test('device revocation covers cancel, stale, success, and failure outcomes', async () => {
  state.confirm
    .mockReturnValueOnce(false)
    .mockReturnValueOnce(true)
    .mockReturnValueOnce(true)
    .mockReturnValueOnce(true)

  state.request.mockResolvedValueOnce({ healthSyncDevices: devices })
  const cancelled = render(React.createElement(HealthSyncPanel))
  await within(cancelled.container).findByText('Current phone')
  fireEvent.click(within(cancelled.container).getAllByRole('button', { name: 'Disconnect' })[0])
  assert.equal(state.request.mock.calls.length, 1)

  cancelled.unmount()

  state.request
    .mockResolvedValueOnce({ healthSyncDevices: devices })
    .mockResolvedValueOnce({ revokeHealthSyncDevice: false })
    .mockResolvedValueOnce({ healthSyncDevices: devices })
  const stale = render(React.createElement(HealthSyncPanel))
  await within(stale.container).findByText('Current phone')

  fireEvent.click(within(stale.container).getAllByRole('button', { name: 'Disconnect' })[0])
  await act(async () => flushPromises())
  assert.match(within(stale.container).getByRole('alert').textContent, /already disconnected/)
  assert.equal(state.request.mock.calls.length, 4)
  stale.unmount()

  state.request
    .mockResolvedValueOnce({ healthSyncDevices: devices })
    .mockResolvedValueOnce({ revokeHealthSyncDevice: true })
    .mockResolvedValueOnce({ healthSyncDevices: [devices[1]] })
  const success = render(React.createElement(HealthSyncPanel))
  await within(success.container).findByText('Current phone')

  fireEvent.click(within(success.container).getAllByRole('button', { name: 'Disconnect' })[0])
  await act(async () => flushPromises())
  assert.equal(within(success.container).queryByText('Current phone'), null)
  assert.ok(within(success.container).getByText('New phone'))

  success.unmount()

  state.request
    .mockResolvedValueOnce({ healthSyncDevices: devices })
    .mockRejectedValueOnce(new Error('revoke failed'))
  const failed = render(React.createElement(HealthSyncPanel))
  await within(failed.container).findByText('Current phone')

  fireEvent.click(within(failed.container).getAllByRole('button', { name: 'Disconnect' })[0])
  await act(async () => flushPromises())
  assert.equal(
    within(failed.container).getByRole('alert').textContent,
    'Could not disconnect the device.',
  )

})

test('steps page maps imported and manual records and reloads after deletion', async () => {
  const records = [
    {
      id: '1', dayId: 2, steps: 1234, kcals: 37.2,
      source: 'health_connect', syncedAt: '2026-08-21T12:00:00Z',
    },
    {
      id: '2', dayId: 3, steps: 5, kcals: 0.15,
      source: 'manual', syncedAt: null,
    },
  ]
  state.request.mockImplementation(async (query) => {
    if (query.includes('HealthSyncDevices')) return { healthSyncDevices: [] }
    if (query.includes('DeleteDaySteps')) return { deleteDaySteps: true }
    return { dayStepsList: records }
  })
  state.confirm.mockReturnValueOnce(false).mockReturnValueOnce(true)

  render(React.createElement(StepsPage))
  await waitFor(() => assert.equal(state.dataTableProps.loading, false))
  const props = state.dataTableProps
  assert.equal(props.data.length, 2)
  assert.equal(props.rowHref(records[0]), '/steps/1')
  assert.equal(props.columns[0].accessor(records[0]), '1')
  assert.equal(props.columns[1].accessor(records[0]), 2)
  assert.equal(props.columns[2].accessor(records[0]), '1,234')
  assert.equal(props.columns[3].accessor(records[0]), 37)
  assert.equal(props.columns[4].accessor(records[0]), 'Health Connect')
  assert.equal(props.columns[4].accessor(records[1]), 'Manual')
  assert.notEqual(props.columns[5].accessor(records[0]), '—')
  assert.equal(props.columns[5].accessor(records[1]), '—')

  await act(async () => props.onDelete(records[0]))
  assert.equal(state.request.mock.calls.filter(([q]) => q.includes('DeleteDaySteps')).length, 0)
  await act(async () => props.onDelete(records[0]))
  assert.equal(state.request.mock.calls.filter(([q]) => q.includes('DeleteDaySteps')).length, 1)
})

test('steps page reports load and delete failures without escaping', async () => {
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  state.request.mockImplementation(async (query) => {
    if (query.includes('HealthSyncDevices')) return { healthSyncDevices: [] }
    throw new Error('request failed')
  })
  state.confirm.mockReturnValue(true)

  render(React.createElement(StepsPage))
  await waitFor(() => assert.equal(state.dataTableProps.loading, false))
  await act(async () => state.dataTableProps.onDelete({ id: '1' }))

  assert.equal(consoleError.mock.calls.length, 2)
  consoleError.mockRestore()
})
