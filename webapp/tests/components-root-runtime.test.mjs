import assert from 'node:assert/strict'
import { afterEach, beforeAll, test, vi } from 'vitest'
import { JSDOM } from 'jsdom'
import React from 'react'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://example.com/' })
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
    constructor(url, base) { super(url, base ?? 'http://example.com/') }
  },
})

// The mobile Sidebar uses requestAnimationFrame for focus management and queries
// matchMedia only while the drawer is open; jsdom provides neither.
globalThis.requestAnimationFrame = (callback) => setTimeout(() => callback(Date.now()), 0)
globalThis.cancelAnimationFrame = (handle) => clearTimeout(handle)
// jsdom defaults document.hidden to true; the dashboard refresh guard checks it.
Object.defineProperty(document, 'hidden', { configurable: true, value: false })
let matchMediaMatches = false
const mediaQueryLists = []
dom.window.matchMedia = (query) => {
  const mediaQueryList = {
    matches: matchMediaMatches,
    media: query,
    listeners: [],
    addEventListener: (type, listener) => {
      if (type === 'change') mediaQueryList.listeners.push(listener)
    },
    removeEventListener: (type, listener) => {
      if (type === 'change') mediaQueryList.listeners = mediaQueryList.listeners.filter((l) => l !== listener)
    },
  }
  mediaQueryLists.push(mediaQueryList)
  return mediaQueryList
}

const rtl = await import('@testing-library/react')
const { act, cleanup, fireEvent, render, screen, waitFor } = rtl.default ?? rtl

const state = {
  pathname: '/',
  search: new URLSearchParams(),
  session: null,
  graphql: null,
  status: 'unauthenticated',
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  signIn: vi.fn(),
  signOut: vi.fn(),
  request: vi.fn(),
  alert: vi.fn(),
}

globalThis.alert = state.alert
globalThis.fetch = async (...args) => {
  const data = await state.request(...args)
  return new Response(JSON.stringify({ data }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

vi.doMock('next/navigation', () => ({
  usePathname: () => state.pathname,
  useSearchParams: () => state.search,
  useRouter: () => ({ push: state.push, replace: state.replace, refresh: state.refresh }),
}))
vi.doMock('next-auth/react', () => ({
  useSession: () => ({ data: state.session, status: state.status }),
  getSession: async () => state.session,
  signIn: (...args) => state.signIn(...args),
  signOut: (...args) => state.signOut(...args),
  SessionProvider: ({ children }) => React.createElement('section', { 'data-testid': 'session-provider' }, children),
}))
vi.doMock('next/link', () => ({
  default: ({ href, children, ...props }) => React.createElement('a', { href, ...props }, children),
}))
vi.doMock('framer-motion', () => ({
  motion: new Proxy({}, {
    get: (_target, tag) => React.forwardRef(function MockMotionComponent({ children, ...props }, ref) {
      return React.createElement(tag, { ...props, ref }, children)
    }),
  }),
}))
vi.doMock('next/font/google', () => ({
  Geist: () => ({ variable: '--font-sans' }),
  Geist_Mono: () => ({ variable: '--font-mono' }),
}))
vi.doMock('graphql-request', () => ({
  gql: (parts, ...values) => String.raw({ raw: parts }, ...values),
  request: (...args) => state.request(...args),
  GraphQLClient: class {
    constructor(endpoint, options) {
      state.graphql = {
        endpoint,
        headers: options.headers,
        fetch: options.fetch,
        request: null,
      }
    }
    async request(query, variables) {
      if (state.graphql) state.graphql.request = [query, variables]
      return state.request(query, variables)
    }
  },
}))

let DataTable, EntityForm, fields, Sidebar, AppShell, Dashboard, HomeClient, Providers, Home, RootLayout, metadata, LoginPage, TestPage

beforeAll(async () => {
  ;({ default: DataTable } = await import('../src/components/DataTable.tsx'))
  ;({ default: EntityForm } = await import('../src/components/EntityForm.tsx'))
  fields = await import('../src/components/FormField.tsx')
  ;({ default: Sidebar } = await import('../src/components/Sidebar.tsx'))
  ;({ default: AppShell } = await import('../src/components/AppShell.tsx'))
  ;({ default: Dashboard } = await import('../src/components/Dashboard.tsx'))
  ;({ default: HomeClient } = await import('../src/app/HomeClient.tsx'))
  ;({ Providers } = await import('../src/app/Providers.tsx'))
  ;({ default: Home } = await import('../src/app/page.tsx'))
  ;({ default: RootLayout, metadata } = await import('../src/app/layout.tsx'))
  ;({ default: LoginPage } = await import('../src/app/login/page.tsx'))
  ;({ default: TestPage } = await import('../src/app/test/page.tsx'))
})

afterEach(() => {
  cleanup()
  state.pathname = '/'
  state.search = new URLSearchParams()
  state.session = null
  state.graphql = null
  state.status = 'unauthenticated'
  matchMediaMatches = false
  mediaQueryLists.length = 0
  for (const fn of [state.push, state.replace, state.refresh, state.signIn, state.signOut, state.request, state.alert]) fn.mockClear()
  state.request.mockClear()
})

const textOrder = (testIds) => testIds.map((id) => screen.getByTestId(id).textContent)

test('DataTable renders loading and custom empty states plus add navigation', () => {
  const columns = [{ key: 'name', label: 'Name', accessor: (row) => row.name }]
  const view = render(React.createElement(DataTable, { columns, data: [], loading: true, addHref: '/items/new', addLabel: 'Create item' }))
  assert.match(view.container.textContent, /Loading/)
  fireEvent.click(screen.getByTestId('add-new-btn'))
  assert.deepEqual(state.push.mock.calls[0], ['/items/new'])
  view.rerender(React.createElement(DataTable, { columns, data: [], emptyMessage: 'Nothing here' }))
  assert.equal(screen.getByTestId('empty-table').textContent.trim(), 'Nothing here')
})

test('DataTable sorts both directions, ignores unsortable columns, navigates rows, and isolates delete clicks', () => {
  const rows = [{ id: 1, name: 'Item 10', note: null }, { id: 2, name: 'Item 2', note: 'x' }]
  const onDelete = vi.fn()
  const columns = [
    { key: 'name', label: 'Name', accessor: (row) => row.name },
    { key: 'note', label: 'Note', accessor: (row) => row.note, sortable: false },
  ]
  render(React.createElement(DataTable, { columns, data: rows, rowHref: (row) => `/items/${row.id}`, onDelete }))
  assert.deepEqual(textOrder(['table-row-1', 'table-row-2']).map((x) => x.replace(/\s/g, '')), ['Item10', 'Item2x'])
  fireEvent.click(screen.getByText('Name'))
  assert.deepEqual(textOrder(['table-row-2', 'table-row-1']).map((x) => x.replace(/\s/g, '')), ['Item2x', 'Item10'])
  fireEvent.click(screen.getByText('Name'))
  assert.deepEqual(textOrder(['table-row-1', 'table-row-2']).map((x) => x.replace(/\s/g, '')), ['Item10', 'Item2x'])
  fireEvent.click(screen.getByText('Note'))
  assert.deepEqual(textOrder(['table-row-1', 'table-row-2']).map((x) => x.replace(/\s/g, '')), ['Item10', 'Item2x'])
  fireEvent.click(screen.getByTestId('table-row-1'))
  assert.deepEqual(state.push.mock.calls[0], ['/items/1'])
  fireEvent.click(screen.getByTestId('delete-btn-2'))
  assert.equal(onDelete.mock.calls.length, 1)
  assert.equal(onDelete.mock.calls[0][0], rows[1])
  assert.equal(state.push.mock.calls.length, 1)
})

test('DataTable safely renders without optional actions and recovers when a sorted column disappears', () => {
  const rows = [{ id: 1, name: 'B' }, { id: 2, name: 'A' }]
  const columns = [{ key: 'name', label: 'Name', accessor: (row) => row.name }]
  const view = render(React.createElement(DataTable, { columns, data: rows }))
  fireEvent.click(screen.getByText('Name'))
  view.rerender(React.createElement(DataTable, { columns: [], data: rows }))
  fireEvent.click(screen.getByTestId('table-row-1'))
  assert.equal(state.push.mock.calls.length, 0)
})

test('DataTable defaults add label and sorts nullable values through both comparator directions', () => {
  const rows = [
    { id: 'row-1', name: 'Beta', code: '2' },
    { id: 'row-2', name: 'Alpha', code: undefined },
    { id: 'row-3', name: 'Gamma', code: '10' },
  ]
  render(React.createElement(DataTable, {
    columns: [
      { key: 'name', label: 'Name', accessor: (row) => row.name },
      { key: 'code', label: 'Code', accessor: (row) => row.code },
    ],
    data: rows,
    addHref: '/rows',
    onDelete: vi.fn(),
    rowHref: (row) => `/rows/${row.id}`,
  }))
  assert.equal(screen.getByTestId('add-new-btn').textContent.includes('Add New'), true)
  fireEvent.click(screen.getByTestId('table-row-row-1'))
  assert.deepEqual(state.push.mock.calls[0], ['/rows/row-1'])
  state.push.mockClear()

  fireEvent.click(screen.getByText('Code'))
  const ascOrder = screen.getAllByTestId(/table-row-/).map((row) => row.getAttribute('data-testid'))
  assert.deepEqual(ascOrder, ['table-row-row-2', 'table-row-row-1', 'table-row-row-3'])

  fireEvent.click(screen.getByText('Code'))
  const descOrder = screen.getAllByTestId(/table-row-/).map((row) => row.getAttribute('data-testid'))
  assert.deepEqual(descOrder, ['table-row-row-3', 'table-row-row-1', 'table-row-row-2'])

  fireEvent.click(screen.getByText('Code'))
  const secondAscOrder = screen.getAllByTestId(/table-row-/).map((row) => row.getAttribute('data-testid'))
  assert.deepEqual(secondAscOrder, ['table-row-row-2', 'table-row-row-1', 'table-row-row-3'])
})

test('form field controls expose constraints, defaults, changes, read-only state, and fallbacks', () => {
  const onChange = vi.fn()
  const { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } = fields
  const view = render(React.createElement('div', null,
    React.createElement(FormField, { label: 'Amount', name: 'amount', value: null, onChange, type: 'number', required: true, placeholder: 'Amount', step: '0.1', min: 0, max: 10, helpText: 'Choose wisely', testId: 'amount-input' }),
    React.createElement(SelectField, { label: 'Choice', name: 'choice', value: null, onChange, options: [{ value: 'a', label: 'Alpha' }], required: true, readOnly: true, helpText: 'Locked', testId: 'choice-input' }),
    React.createElement(TextareaField, { label: 'Notes', name: 'notes', value: null, onChange, required: true, readOnly: true, placeholder: 'Notes', testId: 'notes-input' }),
    React.createElement(CheckboxField, { label: 'Enabled', name: 'enabled', checked: false, onChange, helpText: 'Toggle it', testId: 'enabled-input' }),
    React.createElement(ReadonlyField, { label: 'Unknown', value: null, testId: 'unknown-value' }),
  ))
  const amount = screen.getByTestId('amount-input')
  fireEvent.change(amount, { target: { value: '2.5' } })
  fireEvent.click(screen.getByTestId('enabled-input'))
  assert.deepEqual(onChange.mock.calls.map((call) => call), [['amount', '2.5'], ['enabled', true]])
  assert.equal(amount.required, true)
  assert.equal(amount.min, '0')
  assert.equal(screen.getByTestId('choice-input').disabled, true)
  assert.equal(screen.getByTestId('notes-input').rows, 3)
  assert.equal(screen.getByTestId('notes-input').disabled, true)
  assert.equal(screen.getByTestId('unknown-value').textContent, '—')
  assert.match(view.container.textContent, /Choose wisely.*Locked.*Toggle it/s)
})

test('Form fields keep default required/readOnly behavior when flags are omitted', () => {
  const onChange = vi.fn()
  render(React.createElement('div', null,
    React.createElement(fields.FormField, { label: 'Name', name: 'name', value: 'Ada', onChange }),
    React.createElement(fields.SelectField, { label: 'Mode', name: 'mode', value: '', onChange, options: [{ value: 'x', label: 'X' }] }),
    React.createElement(fields.TextareaField, { label: 'Bio', name: 'bio', value: 'Hello', onChange }),
    React.createElement(fields.CheckboxField, { label: 'Active', name: 'active', checked: false, onChange }),
  ))

  fireEvent.change(screen.getByTestId('field-name'), { target: { value: 'Bob' } })
  fireEvent.change(screen.getByTestId('field-mode'), { target: { value: 'x' } })
  fireEvent.change(screen.getByTestId('field-bio'), { target: { value: 'World' } })
  fireEvent.click(screen.getByTestId('field-active'))

  assert.deepEqual(onChange.mock.calls.map((call) => call), [
    ['name', 'Bob'],
    ['mode', 'x'],
    ['bio', 'World'],
    ['active', true],
  ])
  assert.equal(screen.getByTestId('field-name').required, false)
  assert.equal(screen.getByTestId('field-name').disabled, false)
  assert.equal(screen.getByTestId('field-mode').disabled, false)
  assert.equal(screen.getByTestId('field-bio').disabled, false)
  assert.equal(screen.getByTestId('field-active').disabled, false)
  assert.equal(screen.queryByText('*'), null)
})

test('editable select and textarea use default ids and report changes; checkbox can be disabled; readonly keeps zero', () => {
  const onChange = vi.fn()
  const { SelectField, TextareaField, CheckboxField, ReadonlyField, FormField } = fields
  render(React.createElement('div', null,
    React.createElement(FormField, { label: 'Name', name: 'name', value: 'A', onChange, readOnly: true }),
    React.createElement(SelectField, { label: 'Choice', name: 'choice', value: '', onChange, options: [{ value: 'b', label: 'Beta' }] }),
    React.createElement(TextareaField, { label: 'Notes', name: 'notes', value: 'old', onChange, rows: 5 }),
    React.createElement(CheckboxField, { label: 'Locked', name: 'locked', checked: true, onChange, readOnly: true }),
    React.createElement(ReadonlyField, { label: 'Count', value: 0 }),
  ))
  fireEvent.change(screen.getByTestId('field-choice'), { target: { value: 'b' } })
  fireEvent.change(screen.getByTestId('field-notes'), { target: { value: 'new' } })
  assert.deepEqual(onChange.mock.calls.map((call) => call), [['choice', 'b'], ['notes', 'new']])
  assert.equal(screen.getByTestId('field-name').disabled, true)
  assert.equal(screen.getByTestId('field-locked').disabled, true)
  assert.match(document.body.textContent, /Count0/)
})

test('EntityForm saves, navigates back, toggles fieldsets, renders children, and confirms deletion', async () => {
  const onSave = vi.fn(async () => {})
  const onDelete = vi.fn(async () => {})
  render(React.createElement(EntityForm, {
    title: 'Edit item', backHref: '/items', onSave, onDelete,
    fieldsets: [
      { title: 'Closed', collapsible: true, defaultCollapsed: true, content: React.createElement('span', null, 'Closed content') },
      { title: 'Open', collapsible: true, content: React.createElement('span', null, 'Open content') },
      { title: 'Fixed', content: React.createElement('span', null, 'Fixed content') },
    ],
  }, React.createElement('aside', null, 'Extra child')))
  await screen.findByTestId('form-ready')
  const legends = screen.getAllByText(/Closed|Open|Fixed/).filter((node) => node.tagName === 'LEGEND')
  assert.match(legends[0].parentElement.className, /collapsed/)
  fireEvent.click(legends[0])
  fireEvent.click(legends[1])
  fireEvent.click(legends[2])
  assert.doesNotMatch(legends[0].parentElement.className, /collapsed/)
  assert.match(legends[1].parentElement.className, /collapsed/)
  assert.match(document.body.textContent, /Extra child/)
  fireEvent.click(screen.getByTestId('back-btn'))
  assert.deepEqual(state.push.mock.calls[0], ['/items'])
  fireEvent.submit(screen.getByTestId('form-ready'))
  await waitFor(() => assert.equal(onSave.mock.calls.length, 1))
  assert.deepEqual(state.push.mock.calls[1], ['/items'])
  fireEvent.click(screen.getByTestId('delete-btn'))
  assert.equal(screen.getByTestId('delete-btn').textContent.trim(), 'Confirm Delete')
  assert.equal(onDelete.mock.calls.length, 0)
  fireEvent.click(screen.getByTestId('delete-btn'))
  await waitFor(() => assert.equal(onDelete.mock.calls.length, 1))
  assert.deepEqual(state.push.mock.calls[2], ['/items'])
})

test('EntityForm reports save, route, and delete failures and honors saving state', async () => {
  const saveFailure = { message: 'save failed' }
  const onSave = vi.fn(async () => { throw saveFailure })
  const view = render(React.createElement(EntityForm, { title: 'New', backHref: '/items', onSave, saving: true, fieldsets: [] }))
  await screen.findByTestId('form-ready')
  assert.equal(screen.getByTestId('save-btn').disabled, true)
  assert.match(screen.getByTestId('save-btn').textContent, /Saving/)
  fireEvent.submit(screen.getByTestId('form-ready'))
  await screen.findByTestId('form-error')
  assert.match(screen.getByTestId('form-error').textContent, /API ERROR: save failed/)

  state.push.mockImplementationOnce(() => { throw { message: 'route failed' } })
  view.rerender(React.createElement(EntityForm, { title: 'New', backHref: '/items', onSave: async () => {}, onDelete: async () => { throw new Error('delete failed') }, fieldsets: [] }))
  fireEvent.submit(screen.getByTestId('form-ready'))
  await waitFor(() => assert.match(screen.getByTestId('form-error').textContent, /ROUTE ERROR: route failed/))
  fireEvent.click(screen.getByTestId('delete-btn'))
  fireEvent.click(screen.getByTestId('delete-btn'))
  await waitFor(() => assert.match(screen.getByTestId('form-error').textContent, /delete failed/))
  assert.equal(screen.getByTestId('delete-btn').textContent.trim(), 'Delete')
})

test('EntityForm uses the safe fallback when an error has no message', async () => {
  const originalError = globalThis.Error
  globalThis.Error = function FakeError(message) {
    return { message }
  }
  try {
    const onSave = vi.fn(async () => { throw { someMeta: true } })
    render(React.createElement(EntityForm, { title: 'New', backHref: '/items', onSave, fieldsets: [] }))
    await screen.findByTestId('form-ready')
    fireEvent.submit(screen.getByTestId('form-ready'))
    await screen.findByTestId('form-error')
    assert.match(screen.getByTestId('form-error').textContent, /API ERROR: An error occurred/)
  } finally {
    globalThis.Error = originalError
  }
})

test('EntityForm safely formats string and null failures', async () => {
  const view = render(React.createElement(EntityForm, {
    title: 'New',
    backHref: '/items',
    onSave: async () => { throw 'string failure' },
    fieldsets: [],
  }))
  await screen.findByTestId('form-ready')
  fireEvent.submit(screen.getByTestId('form-ready'))
  await waitFor(() => assert.match(screen.getByTestId('form-error').textContent, /API ERROR: string failure/))

  view.rerender(React.createElement(EntityForm, {
    title: 'New',
    backHref: '/items',
    onSave: async () => { throw null },
    fieldsets: [],
  }))
  fireEvent.submit(screen.getByTestId('form-ready'))
  await waitFor(() => assert.match(screen.getByTestId('form-error').textContent, /API ERROR: An error occurred/))
})

test('EntityForm fallback error path handles delete errors without stack or message', async () => {
  const onSave = vi.fn(async () => {})
  const onDelete = vi.fn(async () => { throw {} })
  render(React.createElement(EntityForm, {
    title: 'New',
    backHref: '/items',
    onSave,
    onDelete,
    fieldsets: [],
  }))
  await screen.findByTestId('form-ready')
  fireEvent.submit(screen.getByTestId('form-ready'))
  await waitFor(() => assert.equal(onSave.mock.calls.length, 1))
  assert.equal(onSave.mock.calls.length, 1)
  fireEvent.click(screen.getByTestId('delete-btn'))
  fireEvent.click(screen.getByTestId('delete-btn'))
  await waitFor(() => assert.equal(onDelete.mock.calls.length, 1))
  await waitFor(() => assert.match(screen.getByTestId('form-error').textContent, /An error occurred/))
})

test('EntityForm falls back to generic error when Error construction is unavailable', async () => {
  const originalError = globalThis.Error
  globalThis.Error = function ErrorNoMessage() { return {} }
  try {
    const onSave = vi.fn(async () => { throw new Error() })
    const view = render(React.createElement(EntityForm, { title: 'New', backHref: '/items', onSave, fieldsets: [] }))
    await screen.findByTestId('form-ready')
    fireEvent.submit(view.container.querySelector('form'))
    await waitFor(() => assert.equal(screen.getByTestId('form-error').textContent, 'An error occurred'))
  } finally {
    globalThis.Error = originalError
  }
})

test('EntityForm shows hydration state and skips delete controls when onDelete is missing', async () => {
  const onSave = vi.fn(async () => {})
  const view = render(React.createElement(EntityForm, {
    title: 'No Delete',
    backHref: '/items',
    onSave,
    fieldsets: [{ title: 'Metadata', content: React.createElement('span', null, 'Child content') }],
  }))
  await waitFor(() => assert.equal(screen.queryByTestId('form-ready').textContent.includes('No Delete'), true))
  assert.equal(screen.queryByTestId('form-hydrating'), null)
  assert.equal(screen.queryByTestId('delete-btn'), null)
  await waitFor(() => assert.equal(screen.getByTestId('form-ready').textContent.includes('No Delete'), true))
  fireEvent.submit(view.container.querySelector('form'))
  await waitFor(() => assert.equal(onSave.mock.calls.length, 1))
  await waitFor(() => assert.equal(state.push.mock.calls.length, 1))
  assert.deepEqual(state.push.mock.calls[0], ['/items'])
})

test('Sidebar hides without a session and renders active links, drawer, and logout for a session', () => {
  const view = render(React.createElement(Sidebar))
  assert.equal(view.container.textContent, '')
  state.session = { user: { name: 'A' } }
  state.pathname = '/products/17'
  view.rerender(React.createElement(Sidebar))
  assert.match(screen.getByTestId('nav-products').className, /active/)
  assert.doesNotMatch(screen.getByTestId('nav-dashboard').className, /active/)
  assert.equal(screen.getAllByRole('link').length, 15)
  assert.ok(screen.getByLabelText('Open navigation menu'))
  assert.equal(screen.getAllByLabelText('Close navigation menu').length, 2)
  assert.ok(screen.getByLabelText('Go to dashboard'))
  fireEvent.click(screen.getByTestId('nav-logout'))
  assert.equal(state.signOut.mock.calls.length, 1)
})

test('Sidebar shows Scan products link and marks it active on /scan', () => {
  state.session = { user: { name: 'A' } }
  state.pathname = '/scan'
  render(React.createElement(Sidebar))
  const scanNavLink = screen.getByTestId('nav-scan-products')
  const productsNavLink = screen.getByTestId('nav-products')
  assert.equal(scanNavLink.getAttribute('href'), '/scan')
  assert.equal(scanNavLink.getAttribute('aria-current'), 'page')
  assert.equal(productsNavLink.getAttribute('aria-current'), null)
  assert.ok(scanNavLink.textContent.includes('Scan products'))
  assert.match(scanNavLink.className, /active/)
})

test('Sidebar matches active links only at path-segment boundaries', () => {
  state.session = { user: { name: 'A' } }
  state.pathname = '/scanner'
  const view = render(React.createElement(Sidebar))
  let scanNavLink = screen.getByTestId('nav-scan-products')
  assert.doesNotMatch(scanNavLink.className, /active/)
  assert.equal(scanNavLink.getAttribute('aria-current'), null)

  state.pathname = '/scan/history'
  view.rerender(React.createElement(Sidebar))
  scanNavLink = screen.getByTestId('nav-scan-products')
  assert.match(scanNavLink.className, /active/)
  assert.equal(scanNavLink.getAttribute('aria-current'), 'page')
})

test('Sidebar mobile drawer traps focus, closes on Escape, toggles inert, and restores on breakpoint change', async () => {
  document.body.innerHTML = '<main class="main-content"></main><header class="mobile-header"></header>'
  matchMediaMatches = true
  state.session = { user: { name: 'A' } }
  const view = render(React.createElement(Sidebar))
  fireEvent.click(screen.getByLabelText('Open navigation menu'))
  await waitFor(() => assert.match(screen.getByTestId('sidebar').className, /open/))
  assert.equal(document.querySelector('.main-content').hasAttribute('inert'), true)
  assert.equal(document.querySelector('.mobile-header').hasAttribute('inert'), true)
  assert.equal(document.body.style.overflow, 'hidden')

  // Escape closes the drawer and restores focus to the menu button.
  fireEvent.keyDown(document, { key: 'Escape' })
  await waitFor(() => assert.doesNotMatch(screen.getByTestId('sidebar').className, /open/))
  await waitFor(() => assert.equal(document.activeElement, screen.getByLabelText('Open navigation menu')))
  assert.equal(document.querySelector('.main-content').hasAttribute('inert'), false)
  assert.equal(document.body.style.overflow, '')

  // Reopening the drawer traps Tab between the first and last focusable elements.
  fireEvent.click(screen.getByLabelText('Open navigation menu'))
  await waitFor(() => assert.match(screen.getByTestId('sidebar').className, /open/))
  const focusables = Array.from(screen.getByTestId('sidebar').querySelectorAll('a[href], button:not([disabled])'))
  assert.ok(focusables.length > 0)
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  last.focus()
  fireEvent.keyDown(document, { key: 'Tab' })
  assert.equal(document.activeElement, first)
  first.focus()
  fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
  assert.equal(document.activeElement, last)

  // An empty drawer leaves the Tab handler inert.
  const querySpy = vi.spyOn(HTMLElement.prototype, 'querySelectorAll')
  querySpy.mockReturnValueOnce([])
  fireEvent.keyDown(document, { key: 'Tab' })
  assert.equal(document.activeElement, last)
  querySpy.mockRestore()

  // A desktop breakpoint change closes the drawer.
  const list = mediaQueryLists[mediaQueryLists.length - 1]
  await act(async () => { list.listeners.forEach((listener) => listener({ matches: false })) })
  await waitFor(() => assert.doesNotMatch(screen.getByTestId('sidebar').className, /open/))

  // Losing the session removes the sidebar entirely.
  fireEvent.click(screen.getByLabelText('Open navigation menu'))
  await waitFor(() => assert.match(screen.getByTestId('sidebar').className, /open/))
  state.session = null
  view.rerender(React.createElement(Sidebar))
  await waitFor(() => assert.equal(view.container.textContent, ''))
})

test('Sidebar closes the drawer and focuses main content when the pathname changes', async () => {
  // tabindex makes the injected main content focusable, mirroring AppShell's markup.
  document.body.innerHTML = '<main class="main-content" tabindex="-1"></main>'
  matchMediaMatches = true
  state.session = { user: { name: 'A' } }
  const view = render(React.createElement(Sidebar))
  fireEvent.click(screen.getByLabelText('Open navigation menu'))
  await waitFor(() => assert.match(screen.getByTestId('sidebar').className, /open/))
  state.pathname = '/plans'
  view.rerender(React.createElement(Sidebar))
  await waitFor(() => assert.doesNotMatch(screen.getByTestId('sidebar').className, /open/))
  await waitFor(() => assert.equal(document.activeElement, document.querySelector('.main-content')))
})


test('Sidebar ignores unrelated keys, avoids Tab wrapping at the middle, and tolerates desktop breakpoint changes', async () => {
  document.body.innerHTML = '<main class="main-content"></main><header class="mobile-header"></header>'
  matchMediaMatches = true
  state.session = { user: { name: 'A' } }
  render(React.createElement(Sidebar))
  fireEvent.click(screen.getByLabelText('Open navigation menu'))
  await waitFor(() => assert.match(screen.getByTestId('sidebar').className, /open/))

  // A key that is neither Escape nor Tab leaves the drawer untouched.
  fireEvent.keyDown(document, { key: 'Enter' })
  assert.match(screen.getByTestId('sidebar').className, /open/)

  // Tab from a middle element does not wrap focus.
  const focusables = Array.from(screen.getByTestId('sidebar').querySelectorAll('a[href], button:not([disabled])'))
  focusables[Math.floor(focusables.length / 2)].focus()
  fireEvent.keyDown(document, { key: 'Tab' })
  assert.equal(document.activeElement, focusables[Math.floor(focusables.length / 2)])

  // A breakpoint change back to mobile is a no-op while the drawer is open.
  const list = mediaQueryLists[mediaQueryLists.length - 1]
  await act(async () => { list.listeners.forEach((listener) => listener({ matches: true })) })
  assert.match(screen.getByTestId('sidebar').className, /open/)

  fireEvent.keyDown(document, { key: 'Escape' })
  await waitFor(() => assert.doesNotMatch(screen.getByTestId('sidebar').className, /open/))
})

test('Sidebar preserves pre-existing inert state and tolerates a missing main element', async () => {
  document.body.innerHTML = '<main class="main-content" inert></main>'
  matchMediaMatches = true
  state.session = { user: { name: 'A' } }
  render(React.createElement(Sidebar))
  document.querySelector('.mobile-header').setAttribute('inert', '')
  fireEvent.click(screen.getByLabelText('Open navigation menu'))
  await waitFor(() => assert.match(screen.getByTestId('sidebar').className, /open/))
  fireEvent.keyDown(document, { key: 'Escape' })
  await waitFor(() => assert.doesNotMatch(screen.getByTestId('sidebar').className, /open/))
  // Cleanup restores overflow but does not strip attributes that were already inert.
  assert.equal(document.querySelector('.main-content').hasAttribute('inert'), true)
  assert.equal(document.querySelector('.mobile-header').hasAttribute('inert'), true)
  assert.equal(document.body.style.overflow, '')

  // Opening the drawer without any main content falls back safely.
  cleanup()
  document.body.innerHTML = ''
  render(React.createElement(Sidebar))
  fireEvent.click(screen.getByLabelText('Open navigation menu'))
  await waitFor(() => assert.match(screen.getByTestId('sidebar').className, /open/))
  fireEvent.keyDown(document, { key: 'Escape' })
  await waitFor(() => assert.doesNotMatch(screen.getByTestId('sidebar').className, /open/))
})

test('Sidebar keeps the drawer closed on desktop viewports', async () => {
  // tabindex makes the injected main content focusable, mirroring AppShell's markup.
  document.body.innerHTML = '<main class="main-content" tabindex="-1"></main>'
  matchMediaMatches = false
  state.session = { user: { name: 'A' } }
  render(React.createElement(Sidebar))
  fireEvent.click(screen.getByLabelText('Open navigation menu'))
  // The drawer effect detects the desktop viewport and closes the drawer again.
  assert.doesNotMatch(screen.getByTestId('sidebar').className, /open/)
  await waitFor(() => assert.equal(document.activeElement, document.querySelector('.main-content')))
})

test('AppShell covers loading, redirect, public child, and authenticated shell decisions', async () => {
  state.status = 'loading'
  const view = render(React.createElement(AppShell, null, React.createElement('span', null, 'Child')))
  assert.ok(screen.getByTestId('session-loading'))
  state.status = 'unauthenticated'
  state.pathname = '/products'
  view.rerender(React.createElement(AppShell, null, React.createElement('span', null, 'Child')))
  assert.ok(screen.getByTestId('auth-redirecting'))
  await waitFor(() => assert.equal(state.replace.mock.calls.length, 1))
  assert.match(state.replace.mock.calls[0][0], /^\/login\?callbackUrl=/)
  state.pathname = '/login'
  view.rerender(React.createElement(AppShell, null, React.createElement('span', null, 'Public child')))
  assert.match(view.container.textContent, /Public child/)
  state.status = 'authenticated'
  state.session = { user: { name: 'A', isStaff: true } }
  state.pathname = '/products'
  view.rerender(React.createElement(AppShell, null, React.createElement('span', null, 'Private child')))
  assert.ok(screen.getByTestId('sidebar'))
  assert.match(view.container.textContent, /Private child/)
})

test('AppShell redirects regular users from staff routes and handles backend reauthentication', async () => {
  state.status = 'authenticated'
  state.session = { user: { name: 'A', isStaff: false } }
  state.pathname = '/products/new'
  const view = render(React.createElement(AppShell, null, 'Protected'))
  assert.ok(screen.getByTestId('auth-redirecting'))
  await waitFor(() => assert.equal(state.replace.mock.calls.length, 1))
  state.session = { error: 'BackendReauthenticationRequired', user: { name: 'A', isStaff: true } }
  state.pathname = '/'
  view.rerender(React.createElement(AppShell, null, 'Protected'))
  await waitFor(() => assert.equal(state.replace.mock.calls.length, 2))
})

const dashboardPayload = (overrides = {}) => ({
  me: {
    firstName: 'Fetched',
    dashboard: {
      latestWeight: 0,
      latestBodyFat: 12,
      goalBodyFat: 10,
      recentMeasurements: [],
      todayNutrition: null,
      ...overrides,
    },
  },
})

test('Dashboard skips fetching while unauthenticated and shows fallback empty states without a token', async () => {
  state.status = 'unauthenticated'
  const view = render(React.createElement(Dashboard))
  assert.equal(state.request.mock.calls.length, 0)

  state.status = 'authenticated'
  state.session = { user: {} }
  state.request.mockImplementation(async () => ({ me: { firstName: null, dashboard: null } }))
  view.rerender(React.createElement(Dashboard))
  await waitFor(() => assert.equal(state.request.mock.calls.length, 1))
  assert.equal(screen.getByTestId('dashboard-greeting').textContent, 'Time to dominate, Athlete!')
  assert.match(document.body.textContent, /No weight logged yet/)
  assert.match(document.body.textContent, /CurrentNot set/)
  assert.match(document.body.textContent, /GoalNot set/)
  assert.match(document.body.textContent, /No plan day found for today/)

  // A dashboard payload with no body composition values shows the empty state.
  cleanup()
  state.request.mockImplementation(async () => dashboardPayload({ latestBodyFat: null, goalBodyFat: null }))
  render(React.createElement(Dashboard))
  await waitFor(() => assert.match(document.body.textContent, /No body composition data yet/))
})

test('Dashboard fetches the dashboard query with timezone offset and bearer authorization', async () => {
  state.status = 'authenticated'
  state.session = { accessToken: 'test-token', user: { name: 'Session Name' } }
  let resolve
  state.request.mockImplementation(() => new Promise((done) => { resolve = done }))
  render(React.createElement(Dashboard))
  await waitFor(() => assert.equal(state.request.mock.calls.length, 1))
  assert.ok(screen.getAllByLabelText('Loading dashboard value').length >= 3)

  const [query, variables] = state.request.mock.calls[0]
  assert.match(query, /dashboard\s*\(/)
  assert.equal(typeof variables.timezoneOffsetMinutes, 'number')
  assert.equal(state.graphql.headers.Authorization, 'Bearer test-token')

  await act(async () => resolve(dashboardPayload({
    latestWeight: 88.2,
    recentMeasurements: [
      { id: 'r1', createdAt: '2026-01-01T00:00:00Z', weight: 81, bodyFatPerc: 20 },
      { id: 'r2', createdAt: '2026-01-02T00:00:00Z', weight: 80.5, bodyFatPerc: 19.8 },
    ],
  })))
  assert.equal(screen.getByTestId('dashboard-greeting').textContent, 'Time to dominate, Fetched!')
  // The latest measurement overrides the summary's latest values.
  assert.match(document.body.textContent, /Current Weight80\.5kg/)
  assert.match(document.body.textContent, /Current19\.8%/)
  assert.match(document.body.textContent, /Goal10%/)
  const trend = screen.getByRole('img', { name: /Weight trend from 81 kilograms to 80\.5 kilograms/ })
  assert.ok(trend)
})

test('Dashboard renders today nutrition with a progress bar and day-linked meal action', async () => {
  state.status = 'authenticated'
  state.session = { accessToken: 't', user: { name: 'N' } }
  const localToday = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
  state.request.mockImplementation(async () => dashboardPayload({
    latestWeight: 88.4,
    latestBodyFat: 22,
    goalBodyFat: 18,
    recentMeasurements: [{ id: 'r1', createdAt: '2026-01-01T00:00:00Z', weight: 88.4, bodyFatPerc: 22 }],
    todayNutrition: { id: 'day-7', day: localToday, energyKcal: 1560, energyKcalGoal: 2000, intakeCount: 4 },
  }))
  render(React.createElement(Dashboard))
  await waitFor(() => assert.ok(screen.getByRole('progressbar')))
  assert.equal(screen.getByRole('progressbar').getAttribute('aria-valuenow'), '1560')
  assert.equal(screen.getByRole('progressbar').getAttribute('aria-valuemax'), '2000')
  assert.match(document.body.textContent, /4 entries logged today/)
  const mealLink = screen.getAllByRole('link').find((link) => link.getAttribute('href') === '/intakes/new?dayId=day-7')
  assert.ok(mealLink)
  // A single measurement leaves the trend below the two-point threshold.
  assert.match(document.body.textContent, /Log at least two measurements to see your trend/)
})

test('Dashboard renders a zero-goal progress bar without dividing by zero', async () => {
  state.status = 'authenticated'
  state.session = { accessToken: 't', user: { name: 'N' } }
  const localToday = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
  state.request.mockImplementation(async () => dashboardPayload({
    todayNutrition: { id: 'day-zero', day: localToday, energyKcal: 1560, energyKcalGoal: 0, intakeCount: 2 },
  }))
  render(React.createElement(Dashboard))
  await waitFor(() => assert.ok(screen.getByRole('progressbar')))
  assert.equal(screen.getByRole('progressbar').getAttribute('aria-valuemax'), '1')
  assert.equal(screen.getByRole('progressbar').style.width, '0%')
})

test('Dashboard shows the empty trend hint and a non-current day fallback', async () => {
  state.status = 'authenticated'
  state.session = { accessToken: 't', user: { name: 'N' } }
  state.request.mockImplementation(async () => dashboardPayload({
    recentMeasurements: [{ id: 'r1', createdAt: '2026-01-01T00:00:00Z', weight: 88.4, bodyFatPerc: 22 }],
    todayNutrition: { id: 'day-old', day: '2020-01-01', energyKcal: 100, energyKcalGoal: 2000, intakeCount: 1 },
  }))
  render(React.createElement(Dashboard))
  await waitFor(() => assert.match(document.body.textContent, /No plan day found for today/))
  assert.match(document.body.textContent, /Log at least two measurements to see your trend/)
})

test('Dashboard signs out when the backend has no current user and surfaces request errors', async () => {
  state.status = 'authenticated'
  state.session = { accessToken: 'test-token', user: { name: 'Session Name' } }
  state.request.mockImplementation(async () => ({ me: null }))
  const view = render(React.createElement(Dashboard))
  await waitFor(() => assert.equal(state.signOut.mock.calls.length, 1))
  assert.deepEqual(state.signOut.mock.calls[0], [{ callbackUrl: '/login' }])
  cleanup()
  const originalError = console.error
  const errors = []
  console.error = (...args) => errors.push(args)
  state.request.mockImplementation(async () => { throw new Error('network down') })
  render(React.createElement(Dashboard))
  await waitFor(() => assert.equal(errors.length, 1))
  assert.equal(errors[0][0], 'Failed to fetch dashboard data')
  assert.match(document.body.textContent, /Dashboard data could not be loaded/)
  console.error = originalError
  view.unmount()
})

test('Dashboard ignores a resolved request after unmount', async () => {
  let resolve
  state.status = 'authenticated'
  state.session = { accessToken: 'test-token', user: { name: 'Session Name' } }
  state.request.mockImplementation(() => new Promise((done) => { resolve = done }))
  const view = render(React.createElement(Dashboard))
  await waitFor(() => assert.equal(state.request.mock.calls.length, 1))
  view.unmount()
  await act(async () => resolve(dashboardPayload({ latestWeight: 1, latestBodyFat: 2, goalBodyFat: 3 })))
  assert.equal(document.body.textContent, '')
})

test('Dashboard ignores a failed request after unmount', async () => {
  let reject
  state.status = 'authenticated'
  state.session = { accessToken: 'test-token', user: { name: 'Session Name' } }
  const originalError = console.error
  const errors = []
  console.error = (...args) => errors.push(args)
  try {
    state.request.mockImplementation(() => new Promise((_done, fail) => { reject = fail }))
    const view = render(React.createElement(Dashboard))
    await waitFor(() => assert.equal(state.request.mock.calls.length, 1))
    view.unmount()
    await act(async () => reject(new Error('late network failure')))
    // The error is logged but the cancelled flag keeps the error state from rendering.
    assert.equal(errors.length, 1)
    assert.doesNotMatch(document.body.textContent, /Dashboard data could not be loaded/)
  } finally {
    console.error = originalError
  }
})

test('Dashboard refreshes on window focus and document visibility changes', async () => {
  state.status = 'authenticated'
  state.session = { accessToken: 't', user: { name: 'N' } }
  state.request.mockImplementation(async () => dashboardPayload())
  render(React.createElement(Dashboard))
  await waitFor(() => assert.equal(state.request.mock.calls.length, 1))
  fireEvent(window, new Event('focus'))
  await waitFor(() => assert.equal(state.request.mock.calls.length, 2))
  // While the document is hidden the visibility handler does not refresh.
  Object.defineProperty(document, 'hidden', { configurable: true, value: true })
  fireEvent(document, new Event('visibilitychange'))
  await new Promise((resolve) => setTimeout(resolve, 50))
  assert.equal(state.request.mock.calls.length, 2)
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  fireEvent(document, new Event('visibilitychange'))
  await waitFor(() => assert.equal(state.request.mock.calls.length, 3))
})

test('Dashboard schedules the midnight refresh and reloads data', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    const { millisecondsUntilNextLocalDay } = await import('../src/components/dashboardHelpers.ts')
    state.status = 'authenticated'
    state.session = { accessToken: 't', user: { name: 'N' } }
    state.request.mockImplementation(async () => dashboardPayload())
    const view = render(React.createElement(Dashboard))
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    assert.equal(state.request.mock.calls.length, 1)
    // The midnight timer fires once and reschedules for the following day.
    await act(async () => { await vi.advanceTimersByTimeAsync(millisecondsUntilNextLocalDay() + 1000) })
    assert.equal(state.request.mock.calls.length, 2)
    // Unmounting clears the pending timer, so no further midnight reloads happen.
    view.unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(millisecondsUntilNextLocalDay() + 1000) })
    assert.equal(state.request.mock.calls.length, 2)
  } finally {
    vi.useRealTimers()
  }
})

test('Dashboard does not reschedule the midnight refresh once cancelled', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  try {
    const { millisecondsUntilNextLocalDay } = await import('../src/components/dashboardHelpers.ts')
    state.status = 'authenticated'
    state.session = { accessToken: 't', user: { name: 'N' } }
    const pending = []
    state.request.mockImplementation(() => {
      if (state.request.mock.calls.length === 1) return Promise.resolve(dashboardPayload())
      return new Promise((resolve) => { pending.push(resolve) })
    })
    const view = render(React.createElement(Dashboard))
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    assert.equal(state.request.mock.calls.length, 1)
    // The midnight reload fires but stays pending while the component unmounts.
    await act(async () => { await vi.advanceTimersByTimeAsync(millisecondsUntilNextLocalDay() + 1000) })
    assert.equal(state.request.mock.calls.length, 2)
    view.unmount()
    await act(async () => { pending.forEach((resolve) => resolve(dashboardPayload())) })
    // The cancelled flag suppresses the reschedule: no third request ever fires.
    await act(async () => { await vi.advanceTimersByTimeAsync(millisecondsUntilNextLocalDay() + 1000) })
    assert.equal(state.request.mock.calls.length, 2)
  } finally {
    vi.useRealTimers()
  }
})

test('HomeClient and root page choose loading, signed-out, and dashboard views', () => {
  state.status = 'loading'
  const view = render(React.createElement(HomeClient))
  assert.match(view.container.textContent, /Loading/)
  state.status = 'unauthenticated'
  view.rerender(React.createElement(HomeClient))
  assert.match(view.container.textContent, /Please sign in/)
  assert.equal(screen.getByRole('link').getAttribute('href'), '/api/auth/signin')
  state.status = 'authenticated'
  state.session = { user: { name: 'Ada Lovelace' } }
  view.rerender(React.createElement(Home))
  assert.equal(screen.getByTestId('dashboard-greeting').textContent, 'Time to dominate, Ada!')
})

test('Providers wraps children, root layout composes the shell, and test page renders', () => {
  const view = render(React.createElement(Providers, null, React.createElement('span', null, 'Provided')))
  assert.equal(screen.getByTestId('session-provider').textContent, 'Provided')

  const layout = RootLayout({ children: 'Layout child' })
  assert.equal(layout.type, 'html')
  assert.equal(layout.props.lang, 'en')
  const body = layout.props.children
  assert.equal(body.type, 'body')
  assert.equal(body.props.className, '--font-sans --font-mono antialiased')
  assert.equal(body.props.children.type, Providers)
  assert.equal(body.props.children.props.children.type, AppShell)
  assert.equal(body.props.children.props.children.props.children, 'Layout child')
  assert.equal(metadata.title, 'Nutrition Tracker')

  view.rerender(React.createElement(TestPage))
  assert.equal(view.container.textContent, 'Test')
})

test('Login submits credentials and navigates to a safe callback on success', async () => {
  state.search = new URLSearchParams('callbackUrl=%2Fproducts%3Fpage%3D2')
  state.signIn.mockImplementation(async () => ({ ok: true }))
  const view = render(React.createElement(LoginPage))
  fireEvent.change(screen.getByPlaceholderText('Email'), { target: { value: 'user@example.com' } })
  fireEvent.change(screen.getByPlaceholderText('Password'), { target: { value: 'secret' } })
  fireEvent.submit(view.container.querySelector('form'))
  await waitFor(() => assert.equal(state.signIn.mock.calls.length, 1))
  assert.deepEqual(state.signIn.mock.calls[0], ['credentials', { email: 'user@example.com', password: 'secret', callbackUrl: '/products?page=2', redirect: false }])
  await waitFor(() => assert.equal(state.push.mock.calls.length, 1))
  assert.equal(state.refresh.mock.calls.length, 1)
  assert.deepEqual(state.push.mock.calls[0], ['/products?page=2'])
})

test('Login shows inline retry guidance and never navigates on rejected credentials', async () => {
  state.search = new URLSearchParams('callbackUrl=https%3A%2F%2Fevil.example.com')
  state.signIn.mockImplementation(async () => ({ ok: false }))
  const view = render(React.createElement(LoginPage))
  fireEvent.submit(view.container.querySelector('form'))
  await waitFor(() =>
    assert.match(view.container.textContent, /check your connection or credentials/i),
  )
  assert.equal(state.alert.mock.calls.length, 0)
  assert.equal(state.push.mock.calls.length, 0)
  assert.match(view.container.textContent, /Sign In/)
})

test('graphqlRequest resolves browser origin endpoint and forwards auth headers', async () => {
  const fetchResult = { result: 'ok' }
  state.session = { user: { name: 'Token User' }, accessToken: 'token-123' }
  state.request.mockImplementation(async () => fetchResult)
  const { graphqlRequest } = await import('../src/lib/graphql.ts')
  const result = await graphqlRequest('query Demo', { key: 7 })

  assert.equal(state.graphql.endpoint, 'http://example.com/graphql/')
  assert.equal(state.graphql.headers.Authorization, 'Bearer token-123')
  assert.deepEqual(state.graphql.request, ['query Demo', { key: 7 }])
  assert.deepEqual(result, fetchResult)
})

test('graphqlRequest falls back to relative endpoint without browser window and without Authorization', async () => {
  const fetchResult = { result: 'anonymous' }
  const originalWindow = globalThis.window
  state.session = { user: { name: 'Tokenless User' } }
  delete process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT
  state.request.mockImplementation(async () => fetchResult)
  globalThis.window = undefined
  try {
    const { graphqlRequest } = await import('../src/lib/graphql.ts')
    const result = await graphqlRequest('query Demo', { key: 11 })
    assert.equal(state.graphql.endpoint, '/graphql/')
    assert.equal(state.graphql.headers.Authorization, undefined)
    assert.deepEqual(state.graphql.request, ['query Demo', { key: 11 }])
    assert.deepEqual(result, fetchResult)
  } finally {
    globalThis.window = originalWindow
    process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT = ''
  }
})

test('graphqlRequest uses configured absolute endpoint without prepending window origin', async () => {
  const fetchResult = { result: 'ok' }
  process.env.NEXT_PUBLIC_GRAPHQL_ENDPOINT = 'https://api.internal.example/graphql/'
  state.session = { user: { name: 'Token User' }, accessToken: 'token-123' }
  state.request.mockImplementation(async () => fetchResult)
  const { graphqlRequest } = await import('../src/lib/graphql.ts')
  const result = await graphqlRequest('query Demo', { key: 13 })

  assert.equal(state.graphql.endpoint, 'https://api.internal.example/graphql/')
  assert.equal(state.graphql.headers.Authorization, 'Bearer token-123')
  assert.deepEqual(state.graphql.request, ['query Demo', { key: 13 }])
  assert.deepEqual(result, fetchResult)
})
