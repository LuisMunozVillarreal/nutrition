import assert from 'node:assert/strict'
import { afterEach, test, vi } from 'vitest'
import React from 'react'
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' })
for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Node', 'Event', 'MouseEvent', 'getComputedStyle']) {
  Object.defineProperty(globalThis, key, { configurable: true, value: dom.window[key] })
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const rtl = await import('@testing-library/react')
const { act, fireEvent, render } = rtl.default ?? rtl
let view
let session = { user: { isStaff: false } }
const push = vi.fn()
const products = [
  { id: 'p1', name: 'Rolled oats', brand: null, size: 500, sizeUnit: 'g' },
  { id: 'p2', name: 'Milk', brand: 'Farm', size: 1, sizeUnit: 'l' },
]
let request = vi.fn(async () => ({ foodProducts: products }))
vi.doMock('next-auth/react', () => ({ useSession: () => ({ data: session }) }))
vi.doMock('next/navigation', () => ({ useRouter: () => ({ push }) }))
vi.doMock('@/lib/graphql', () => ({
  gql: (parts, ...values) => String.raw({ raw: parts }, ...values),
  graphqlRequest: (...args) => request(...args),
}))
afterEach(async () => {
  await act(async () => { view?.unmount() })
  view = undefined
  session = { user: { isStaff: false } }
  request = vi.fn(async () => ({ foodProducts: products }))
  push.mockClear()
})

test('Products searches names and brands without requiring a barcode and preserves staff controls', async () => {
  const { default: Page } = await import('../src/app/products/page.tsx')
  await act(async () => { view = render(React.createElement(Page)) })
  const input = view.queryByRole('searchbox', { name: 'Search products' })
  assert.ok(input, 'Products must offer a labelled search input')
  fireEvent.change(input, { target: { value: '  OATS ' } })
  assert.ok(view.queryByText('Rolled oats'))
  assert.equal(view.queryByText('Milk'), null)
  fireEvent.change(input, { target: { value: 'fArM' } })
  assert.ok(view.queryByText('Milk'))
  assert.equal(view.queryByText('Rolled oats'), null)
  fireEvent.click(view.getByText('Milk'))
  assert.equal(push.mock.calls.length, 0)
  assert.equal(view.queryByText('New Product'), null)
  fireEvent.change(input, { target: { value: 'missing' } })
  assert.ok(view.queryByText('No products match your search.'))
  fireEvent.change(input, { target: { value: '   ' } })
  assert.ok(view.queryByText('Rolled oats'))
  assert.ok(view.queryByText('Milk'))
  session = { user: { isStaff: true } }
  view.rerender(React.createElement(Page))
  fireEvent.click(view.getByText('Milk'))
  assert.equal(push.mock.calls.at(-1)[0], '/products/p2')
  assert.ok(view.queryByText('New Product'))
  assert.equal(request.mock.calls.length, 1)
})

test('product chooser loads on demand, filters the complete catalog and clears results', async () => {
  const { default: ProductSearch } = await import('../src/components/ProductSearch.tsx')
  const select = vi.fn()
  const start = vi.fn()
  let resolve
  request = vi.fn(() => new Promise((done) => { resolve = done }))
  await act(async () => { view = render(React.createElement(ProductSearch, { onSelect: select, onSearchStart: start })) })
  assert.equal(request.mock.calls.length, 0)
  const input = view.getByRole('searchbox', { name: 'Search products' })
  fireEvent.focus(input)
  assert.equal(start.mock.calls.length, 1)
  await act(async () => { fireEvent.change(input, { target: { value: '  ' } }) })
  assert.equal(request.mock.calls.length, 0)
  await act(async () => { fireEvent.change(input, { target: { value: '  FARM ' } }) })
  assert.ok(view.queryByText('Loading products...'))
  await act(async () => { resolve({ foodProducts: products }) })
  assert.equal(view.queryByRole('button', { name: /Select Rolled oats/ }), null)
  fireEvent.click(view.getByRole('button', { name: /Select Farm Milk/ }))
  assert.deepEqual(select.mock.calls, [[products[1]]])
  fireEvent.change(input, { target: { value: 'oats' } })
  assert.ok(view.queryByRole('button', { name: /Select Rolled oats/ }))
  fireEvent.change(input, { target: { value: 'missing' } })
  assert.ok(view.queryByText('No products match your search.'))
  fireEvent.change(input, { target: { value: '' } })
  assert.equal(view.queryByRole('button'), null)
  assert.equal(view.queryByText('No products match your search.'), null)
  assert.equal(request.mock.calls.length, 1)
})

test('product chooser reports a loading failure and allows retry', async () => {
  const { default: ProductSearch } = await import('../src/components/ProductSearch.tsx')
  request = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ foodProducts: products })
  await act(async () => { view = render(React.createElement(ProductSearch, { onSelect: vi.fn(), onSearchStart: vi.fn() })) })
  await act(async () => { fireEvent.change(view.getByRole('searchbox'), { target: { value: 'oats' } }) })
  assert.match(view.getByRole('alert').textContent, /Could not load products/)
  await act(async () => { fireEvent.click(view.getByRole('button', { name: 'Retry product search' })) })
  assert.ok(view.queryByRole('button', { name: /Select Rolled oats/ }))
  assert.equal(view.queryByRole('alert'), null)
})

test.each(['resolve', 'reject'])('product chooser ignores a late %s after unmount', async (outcome) => {
  const { default: ProductSearch } = await import('../src/components/ProductSearch.tsx')
  let finish
  request = vi.fn(() => new Promise((resolve, reject) => { finish = outcome === 'resolve' ? resolve : reject }))
  const select = vi.fn()
  await act(async () => { view = render(React.createElement(ProductSearch, { onSelect: select, onSearchStart: vi.fn() })) })
  await act(async () => { fireEvent.change(view.getByRole('searchbox'), { target: { value: 'oats' } }) })
  await act(async () => { view.unmount() })
  view = undefined
  await act(async () => { finish(outcome === 'resolve' ? { foodProducts: products } : new Error('late')) })
  assert.equal(select.mock.calls.length, 0)
})
