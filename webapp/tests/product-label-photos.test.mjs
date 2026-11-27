// @vitest-environment jsdom
import assert from 'node:assert/strict'
import React from 'react'
import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, test, vi } from 'vitest'
import Page from '../src/app/products/new/page.tsx'

const { request, push } = vi.hoisted(() => ({ request: vi.fn(), push: vi.fn() }))
let params = new URLSearchParams()
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }), useSearchParams: () => params }))
vi.mock('@/lib/graphql', () => ({ gql: String.raw, graphqlRequest: request }))
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  request.mockReset()
  push.mockReset()
  params = new URLSearchParams()
})

const jpeg = 'data:image/jpeg;base64,AAAA'
function camera() {
  vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width: 3000, height: 1500, close: vi.fn() })))
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: vi.fn(), fillRect: vi.fn() })
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue(jpeg)
}
const photo = () => new File(['pixels'], 'label.png', { type: 'image/png' })
const label = draft => ({ extractProductLabel: { draftJson: JSON.stringify(draft) } })
function choose(view, files = [photo()]) {
  fireEvent.change(view.getByLabelText('Label photos'), { target: { files } })
}
async function click(view, name) {
  await act(async () => fireEvent.click(view.getByRole('button', { name })))
}

test('photos fill the existing form for review; Save uses corrections and meal context', async () => {
  camera()
  params = new URLSearchParams('labelPhotos=1&barcode=00123&fromBarcodeScan=1&fromMealLog=1&intakeDayDate=2026-01-01&intakeMeal=lunch&intakeNumServings=3')
  const view = render(React.createElement(Page))
  const field = key => view.getByTestId('field-' + key)
  const edit = (key, value) => fireEvent.change(field(key), { target: { value } })
  edit('brand', 'My brand')
  choose(view, [photo(), photo()])
  request.mockResolvedValueOnce(label({ name: 'Oats', brand: 'Wrong', barcode: null, size: null, energyKcal: 94, fatG: 0, carbsG: 20, proteinG: 2 }))
  await click(view, 'Read labels')
  assert.match(request.mock.calls[0][0], /mutation .*\(\$photos: \[String!\]!\)/)
  assert.deepEqual(request.mock.calls[0][1], { photos: [jpeg, jpeg] })
  assert.equal(request.mock.calls.length, 1)
  assert.equal(view.getAllByRole('img').length, 2)
  assert.equal(field('brand').value, 'My brand')
  assert.equal(field('barcode').value, '00123')
  assert.equal(field('name').value, 'Oats')
  assert.equal(field('fatG').value, '0')
  for (const key of ['size', 'sizeUnit', 'nutritionalInfoSize', 'nutritionalInfoUnit', 'numServings']) assert.equal(field(key).value, '')
  assert.match(view.getByRole('status').textContent, /Package size/)
  await click(view, 'Save')
  assert.equal(request.mock.calls.length, 1)
  for (const [key, value] of Object.entries({ name: 'Rolled oats', size: '500', sizeUnit: 'g', nutritionalInfoSize: '100', nutritionalInfoUnit: 'g', numServings: '5' })) edit(key, value)
  request.mockResolvedValueOnce({ foodProductByBarcode: { product: null } }).mockResolvedValueOnce({ createFoodProduct: { id: 'p5' } })
  await click(view, 'Save')
  assert.deepEqual(request.mock.calls[1][1], { barcode: '00123' })
  assert.equal(request.mock.calls[2][1].name, 'Rolled oats')
  assert.equal(request.mock.calls[2][1].numServings, 5)
  assert.equal(request.mock.calls[2][1].fatG, 0)
  assert.equal(push.mock.calls[0][0], '/intakes/new?dayDate=2026-01-01&productId=p5&intakeMeal=lunch&intakeNumServings=3')
})

test('four detailed photos fit the batch request without cropping', async () => {
  camera()
  const large = 'data:image/jpeg;base64,' + 'A'.repeat(800000)
  const small = 'data:image/jpeg;base64,' + 'A'.repeat(400000)
  const sizes = []
  HTMLCanvasElement.prototype.toDataURL.mockImplementation(function (type) {
    assert.equal(type, 'image/jpeg')
    sizes.push([this.width, this.height])
    return this.width >= 2560 ? large : small
  })
  const view = render(React.createElement(Page))
  await click(view, 'Create from label photos')
  choose(view, Array.from({ length: 4 }, photo))
  request.mockResolvedValueOnce(label({}))
  await click(view, 'Read labels')
  const { photos } = request.mock.calls[0][1]
  assert.equal(photos.length, 4)
  assert.ok(photos.every(src => src.length <= 1024 ** 2))
  assert.ok(photos.reduce((n, src) => n + atob(src.split(',')[1]).length, 0) <= 1.5 * 1024 ** 2)
  assert.ok(sizes.every(([width, height]) => width === height * 2))
})


const complete = { name: 'Tea', size: 10, sizeUnit: 'g', numServings: 1, nutritionalInfoSize: 100, nutritionalInfoUnit: 'g', energyKcal: 0, proteinG: 0, carbsG: 0, fatG: 0, saltG: 0.02 }

test('decimal label values can be saved; a duplicate barcode blocks creation', async () => {
  camera()
  const view = render(React.createElement(Page))
  await click(view, 'Create from label photos')
  choose(view)
  request.mockResolvedValueOnce(label({ ...complete, barcode: '0045' }))
  await click(view, 'Read labels')
  assert.equal(view.getByTestId('field-saltG').checkValidity(), true)
  request.mockResolvedValueOnce({ foodProductByBarcode: { product: { name: 'Other tea' } } })
  await click(view, 'Save')
  assert.match(view.getByTestId('form-error').textContent, /already belongs to Other tea/)
  assert.equal(request.mock.calls.length, 2)
  fireEvent.change(view.getByTestId('field-barcode'), { target: { value: '' } })
  request.mockResolvedValueOnce({ createFoodProduct: { id: 'tea' } })
  await click(view, 'Save')
  assert.equal(request.mock.calls[2][1].saltG, 0.02)
  assert.equal(request.mock.calls[2][1].barcode, null)
  assert.equal(push.mock.calls[0][0], '/products')
})


test('invalid selections and failed reads are retryable without changing the form', async () => {
  camera()
  const view = render(React.createElement(Page))
  await click(view, 'Create from label photos')
  choose(view, Array.from({ length: 5 }, photo))
  assert.match(view.getByRole('alert').textContent, /at most four/)
  assert.equal(view.getByRole('button', { name: 'Read labels' }).disabled, true)
  choose(view, [photo(), photo()])
  fireEvent.click(view.getAllByRole('button', { name: 'Remove' })[0])
  for (const draft of [null, [], 'broken']) {
    request.mockResolvedValueOnce(label(draft))
    await click(view, 'Read labels')
    assert.match(view.getByRole('alert').textContent, /Retry/)
    assert.deepEqual(request.mock.lastCall[1], { photos: [jpeg] })
    assert.equal(view.getByTestId('field-size').value, '100')
  }
  request.mockResolvedValueOnce(label({ name: 'Tea' }))
  await click(view, 'Read labels')
  assert.equal(view.getByTestId('field-size').value, '')
  assert.equal(view.getByTestId('field-name').value, 'Tea')
  fireEvent.change(view.getByTestId('field-name'), { target: { value: 'My tea' } })
  await click(view, 'Read new photos')
  choose(view)
  request.mockResolvedValueOnce(label({ name: 'Uncorrected tea', size: 50 }))
  await click(view, 'Read labels')
  assert.equal(view.getByTestId('field-name').value, 'My tea')
  assert.equal(view.getByTestId('field-size').value, '50')
})

test.each(['decode', 'extract', 'failed extract'])('cancel during %s ignores late work', async stage => {
  camera()
  const pending = Promise.withResolvers()
  if (stage === 'decode') createImageBitmap.mockReturnValueOnce(pending.promise)
  else request.mockReturnValueOnce(pending.promise)
  const view = render(React.createElement(Page))
  await click(view, 'Create from label photos')
  choose(view)
  await click(view, 'Read labels')
  await click(view, 'Cancel photos')
  fireEvent.change(view.getByTestId('field-name'), { target: { value: 'Manual tea' } })
  await act(async () => {
    if (stage === 'decode') pending.resolve({ width: 100, height: 100, close: vi.fn() })
    else if (stage === 'extract') pending.resolve(label({ name: 'Stale tea' }))
    else pending.reject(new Error('Request failed'))
  })
  assert.equal(request.mock.calls.length, stage === 'decode' ? 0 : 1)
  assert.equal(view.getByTestId('field-name').value, 'Manual tea')
  assert.equal(view.getByTestId('field-size').value, '100')
  assert.equal(view.queryByRole('img'), null)
  assert.equal(view.queryByRole('alert'), null)
  assert.equal(view.getByRole('button', { name: 'Save' }).disabled, false)
})

test.each(['no canvas', 'oversize', 'not JPEG'])('conversion fails closed for %s and releases the bitmap', async cause => {
  camera()
  const close = vi.fn()
  createImageBitmap.mockResolvedValue({ width: 1000, height: 600, close })
  if (cause === 'no canvas') HTMLCanvasElement.prototype.getContext.mockReturnValue(null)
  else HTMLCanvasElement.prototype.toDataURL.mockReturnValue(cause === 'oversize' ? jpeg + 'A'.repeat(1024 ** 2) : 'data:,')
  const view = render(React.createElement(Page))
  await click(view, 'Create from label photos')
  choose(view)
  await click(view, 'Read labels')
  assert.match(view.getByRole('alert').textContent, /choose clearer photos/)
  assert.equal(request.mock.calls.length, 0)
  assert.equal(close.mock.calls.length, 1)
})


test('incompatible units need review rather than saving a hidden or inferred unit', async () => {
  camera()
  const view = render(React.createElement(Page))
  await click(view, 'Create from label photos')
  const submit = () => act(async () => fireEvent.submit(view.getByTestId('form-ready')))
  await submit()
  assert.match(view.getByTestId('form-error').textContent, /cancel photos/)
  choose(view)
  request.mockResolvedValueOnce(label({ ...complete, nutritionalInfoUnit: 'ml' }))
  await click(view, 'Read labels')
  assert.match(view.getByRole('status').textContent, /Info unit base/)
  await submit()
  assert.match(view.getByTestId('form-error').textContent, /Complete required fields: Info unit base/)
  assert.equal(request.mock.calls.length, 1)
})


test('a retry keeps the reviewed basis unit when the new package unit conflicts', async () => {
  camera()
  params = new URLSearchParams('labelPhotos=1')
  const view = render(React.createElement(Page))
  choose(view)
  request.mockResolvedValueOnce(label({ nutritionalInfoUnit: 'g' }))
  await click(view, 'Read labels')
  fireEvent.change(view.getByTestId('field-nutritionalInfoUnit'), { target: { value: 'kg' } })
  await click(view, 'Read new photos')
  choose(view)
  request.mockResolvedValueOnce(label({ sizeUnit: 'ml' }))
  await click(view, 'Read labels')
  assert.equal(view.getByTestId('field-nutritionalInfoUnit').value, 'kg')
  assert.equal(view.getByTestId('field-sizeUnit').value, '')
})
