import React from 'react'
import { JSDOM } from 'jsdom'
import { afterEach, expect, test, vi } from 'vitest'
const dom = new JSDOM('<html><body></body></html>', { url: 'https://example.com/' })
Object.assign(globalThis, { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, Node: dom.window.Node, IS_REACT_ACT_ENVIRONMENT: true })
const query = new URLSearchParams({ issuer: 'https://example.com', redirect_uri: 'com.nutrition.healthsync:/oauth2redirect', code_challenge: 'a'.repeat(43), code_challenge_method: 'S256', state: 's'.repeat(43), device_name: 'Phone' })
const state = { query, session: { user: { email: 'user@example.com' }, accessToken: 'jwt' }, consent: vi.fn() }
vi.doMock('next/navigation', () => ({ useSearchParams: () => state.query }))
vi.doMock('next-auth/react', () => ({ useSession: () => ({ data: state.session }) }))
vi.doMock('@/lib/healthAuthorization', async () => {
  const real = await import('../src/lib/healthAuthorization')
  return { ...real, consentRedirect: (...args) => state.consent(...args) }
})
const { render, screen, fireEvent, waitFor, cleanup } = await import('@testing-library/react')
const { default: Page } = await import('../src/app/health-sync/authorize/page')
afterEach(() => { cleanup(); state.query = query; state.consent.mockReset() })
test('requires an explicit consent click and shows the signed-in account', async () => {
  state.consent.mockRejectedValue(new Error('Unavailable'))
  render(React.createElement(Page))
  expect(screen.getByText(/user@example.com/)).toBeTruthy()
  expect(state.consent).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Connect phone' }))
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('Could not connect'))
  expect(state.consent).toHaveBeenCalledWith(expect.objectContaining({ device_name: 'Phone' }), 'jwt')
})
test('successful consent returns to Android without rendering credentials', async () => {
  const assign = vi.fn()
  const browser = Object.create(dom.window)
  Object.defineProperty(browser, 'location', { value: { origin: 'https://example.com', assign } })
  globalThis.window = browser
  state.consent.mockResolvedValue('com.nutrition.healthsync:/oauth2redirect?code=opaque')
  render(React.createElement(Page))
  expect(screen.getByRole('link', { name: 'Cancel' }).href).toContain('error=access_denied')
  fireEvent.click(screen.getByRole('button', { name: 'Connect phone' }))
  await waitFor(() => expect(assign).toHaveBeenCalled())
  globalThis.window = dom.window
})

test('invalid parameters cannot create a grant or offer a redirect', () => {
  state.query = new URLSearchParams('redirect_uri=https://evil.example.com')
  render(React.createElement(Page))
  expect(screen.getByRole('alert').textContent).toContain('Invalid')
  expect(screen.queryByRole('button')).toBeNull()
})
