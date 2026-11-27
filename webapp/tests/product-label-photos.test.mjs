// @vitest-environment jsdom
import assert from 'node:assert/strict'
import React from 'react'
import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, test, vi } from 'vitest'
import EditPage from '../src/app/products/[id]/page.tsx'
import Page from '../src/app/products/new/page.tsx'

const { request, push } = vi.hoisted(() => ({ request: vi.fn(), push: vi.fn() }))
let params = new URLSearchParams()
vi.mock('next/navigation', () => ({ useParams: () => ({ id: 'tea' }), useRouter: () => ({ push }), useSearchParams: () => params }))
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
function pngHeader(width, height) {
  const bytes = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 0, 0, 0, 0, 0])
  const header = new DataView(bytes.buffer)
  header.setUint32(16, width)
  header.setUint32(20, height)
  return bytes
}
const photo = () => new File([pngHeader(3000, 1500)], 'label.png', { type: 'image/png' })
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
  await act(async () => fireEvent.submit(view.getByTestId('form-ready')))
  assert.match(view.getByTestId('form-error').textContent, /Complete required fields:.*Package size/)
  assert.equal(request.mock.calls.length, 1)
  for (const [key, value] of Object.entries({ name: 'Rolled oats', size: '500', sizeUnit: 'g', nutritionalInfoSize: '100', nutritionalInfoUnit: 'g', numServings: '5' })) edit(key, value)
  request.mockResolvedValueOnce({ foodProductByBarcode: { product: null } }).mockResolvedValueOnce({ createFoodProduct: { id: 'p5' } })
  await click(view, 'Save')
  assert.match(request.mock.calls[1][0], /foodProductByBarcode\(barcode: \$barcode, localOnly: true\)/)
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

test.each(['nutritionalInfoSize', 'proteinG'])('a retained %s keeps its entire nutrition column only by explicit choice', async key => {
  camera()
  params = new URLSearchParams('labelPhotos=1')
  const view = render(React.createElement(Page))
  const field = key => view.getByTestId('field-' + key)
  choose(view)
  request.mockResolvedValueOnce(label({ ...complete, energyKcal: 15 }))
  await click(view, 'Read labels')
  await click(view, 'Read new photos')
  choose(view)
  const pending = Promise.withResolvers()
  request.mockReturnValueOnce(pending.promise)
  await click(view, 'Read labels')
  fireEvent.change(field(key), { target: { value: '30' } })
  await act(async () => pending.resolve(label({ ...complete, name: 'New tea', nutritionalInfoSize: 50, energyKcal: 45, saltG: null })))
  assert.match(view.getByRole('alert').textContent, /nutrition column/i)
  assert.equal(field('name').value, 'Tea')
  assert.equal(view.getByRole('button', { name: 'Save' }).disabled, true)
  await click(view, 'Keep my nutrition column')
  assert.equal(field('name').value, 'New tea')
  assert.equal(field(key).value, '30')
  assert.equal(field('energyKcal').value, '15')
  assert.equal(field('saltG').value, '0.02')
})

test('a wrong GTIN rejects the whole batch; equivalent padded UPC can be retried', async () => {
  camera()
  params = new URLSearchParams('fromBarcodeScan=1&labelPhotos=1&barcode=036000291452')
  const view = render(React.createElement(Page))
  choose(view)
  fireEvent.change(view.getByTestId('field-brand'), { target: { value: 'My brand' } })
  request.mockResolvedValueOnce(label({ ...complete, barcode: '4006381333931' }))
  await click(view, 'Read labels')
  assert.match(view.getByRole('alert').textContent, /barcode.*does not match/i)
  assert.equal(view.getByTestId('field-name').value, '')
  assert.equal(view.queryByRole('img'), null)
  await click(view, 'Remove')
  choose(view)
  request.mockResolvedValueOnce(label({ ...complete, barcode: ' 00036000291452 ' }))
  await click(view, 'Read labels')
  assert.equal(view.getByTestId('field-name').value, complete.name)
  assert.equal(view.getByTestId('field-barcode').value, '036000291452')
  assert.equal(view.getByTestId('field-brand').value, 'My brand')
})

test('an existing product with hundredths in every nutrient can be edited and saved', async () => {
  const nutrients = Object.fromEntries(['energyKcal', 'proteinG', 'fatG', 'carbsG', 'saturatedFatG', 'sugarsG', 'fibreG', 'saltG'].map(key => [key, 0.02]))
  request.mockResolvedValueOnce({ foodProduct: { ...complete, ...nutrients, notes: '', servings: [] } })
  const view = await act(async () => render(React.createElement(EditPage)))
  for (const key of Object.keys(nutrients)) assert.equal(view.getByTestId('field-' + key).checkValidity(), true, key)
  fireEvent.change(view.getByTestId('field-name'), { target: { value: 'My tea' } })
  await click(view, 'Save')
  const update = request.mock.calls[1][1]
  assert.equal(update.name, 'My tea')
  for (const key of Object.keys(nutrients)) assert.equal(update[key], 0.02)
})

test.each([
  ['file size', new File([new Uint8Array(16 * 1024 ** 2 + 1)], 'large.png')],
  ['PNG pixels', new File([pngHeader(6000, 5000)], 'large.png')],
  ['PNG edge', new File([pngHeader(9000, 1)], 'wide.png')],
  ['zero dimension', new File([pngHeader(1, 0)], 'invalid.png')],
  ['unknown format', new File(['not an image'], 'fake.jpg')],
  ['invalid segment length', new File([Uint8Array.of(255, 216, 255, 224, 0, 1)], 'bad.jpg')],
  ['missing frame before scan', new File([Uint8Array.of(255, 216, 255, 218, 0, 2)], 'scan.jpg')],
  ['truncated JPEG', new File([Uint8Array.of(255, 216, 255)], 'short.jpg')],
  ['JPEG pixels', new File([Uint8Array.of(255, 216, 255, 192, 0, 17, 8, 32, 0, 32, 0)], 'large.jpg')],
])('rejects %s before bitmap decoding or submission', async (_, file) => {
  camera()
  params = new URLSearchParams('labelPhotos=1')
  const view = render(React.createElement(Page))
  choose(view, [file])
  await click(view, 'Read labels')
  assert.equal(createImageBitmap.mock.calls.length, 0)
  assert.equal(request.mock.calls.length, 0)
  assert.match(view.getByRole('alert').textContent, /JPEG or PNG/)
})

test('JPEG frame dimensions can follow padding, metadata and quantization tables', async () => {
  camera()
  params = new URLSearchParams('labelPhotos=1&barcode=036000291453') // invalid check digit, not a GTIN
  const view = render(React.createElement(Page))
  const header = Uint8Array.of(255, 216, 255, 255, 224, 0, 4, 0, 0, 255, 219, 0, 2, 255, 194, 0, 17, 8, 5, 220, 11, 184)
  choose(view, [new File([header], 'label.jpg', { type: 'image/jpeg' })])
  request.mockResolvedValueOnce(label({ ...complete, barcode: '036000291452' }))
  await click(view, 'Read labels')
  assert.equal(view.getByTestId('field-name').value, complete.name)
  assert.deepEqual(request.mock.calls[0][1], { photos: [jpeg] })
})

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
  assert.match(view.container.textContent, /Read labels.*send.*Google Gemini/i)
  assert.equal(request.mock.calls.length, 0)
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
  assert.match(view.getByRole('alert').textContent, /package unit.*nutrition unit/i)
  assert.equal(view.getByTestId('field-energyKcal').value, '')
  await submit()
  assert.match(view.getByTestId('form-error').textContent, /cancel photos/)
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
  assert.match(view.getByRole('alert').textContent, /package unit.*nutrition unit/i)
  assert.equal(view.getByTestId('field-nutritionalInfoUnit').value, 'kg')
  assert.equal(view.getByTestId('field-sizeUnit').value, '')
})
