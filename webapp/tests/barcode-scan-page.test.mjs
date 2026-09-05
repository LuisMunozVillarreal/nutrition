import assert from 'node:assert/strict'
import { afterEach, test, vi } from 'vitest'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/',
})
const NativeURL = globalThis.URL
for (const key of [
  'window',
  'document',
  'navigator',
  'HTMLElement',
  'Node',
  'Event',
  'MouseEvent',
  'getComputedStyle',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  })
}
globalThis.URL = class TestURL extends NativeURL {
  constructor(url, base) {
    super(url, base ?? 'http://localhost/')
  }
}
globalThis.requestAnimationFrame = (callback) =>
  setTimeout(() => callback(Date.now()), 0)
globalThis.cancelAnimationFrame = (handle) => clearTimeout(handle)
Object.defineProperty(document, 'hidden', { configurable: true, value: false })
globalThis.IS_REACT_ACT_ENVIRONMENT = true

// Imported after the DOM globals are installed, mirroring the repo's
// component test setup; a static import evaluates the library too early.
const rtl = await import('@testing-library/react')
const { act, fireEvent, render } = rtl.default ?? rtl

let push = vi.fn()
let session = { user: { isStaff: true } }
let graphqlImpl = async () => ({})
let graphqlCalls = []
let supported = false
let detector = null
let cameraResult = null
let cameraImpl = async () => cameraResult
let scanResult = null
let scanSignals = []
let stopCalls = []
let detectorCreateCalls = 0
let cameraStartCalls = 0
let frozenFrame = false
let captureCalls = []
let scanSearchParams = new URLSearchParams()
const router = { push }

vi.doMock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => scanSearchParams,
}))
vi.doMock('next-auth/react', () => ({ useSession: () => ({ data: session }) }))
vi.doMock('next/link', () => ({
  default: ({ href, children, ...props }) =>
    React.createElement('a', { href, ...props }, children),
}))
vi.doMock('@/lib/graphql', () => ({
  gql: (parts, ...values) => String.raw({ raw: parts }, ...values),
  graphqlRequest: async (...args) => {
    graphqlCalls.push(args)
    return graphqlImpl(...args)
  },
}))
vi.doMock('@/lib/barcodeScanner', () => ({
  isBarcodeDetectorSupported: () => supported,
  createBarcodeDetector: async () => {
    detectorCreateCalls += 1
    return detector
  },
  startCameraStream: async (...args) => {
    cameraStartCalls += 1
    return cameraImpl(...args)
  },
  stopCameraStream: (stream) => {
    if (stream) stopCalls.push(stream)
  },
  captureVideoFrame: (...args) => {
    captureCalls.push(args)
    return frozenFrame
  },
  readBarcodeFromVideo: async (_video, _detector, signal) => {
    scanSignals.push(signal)
    return scanResult
  },
}))

let mountedView

async function mount() {
  const { default: Page } = await import('../src/app/scan/page.tsx')
  mountedView = render(React.createElement(Page))
  return mountedView.container
}

async function settle(check) {
  let lastError
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await act(async () => {
      await new Promise((resolve) => setImmediate(resolve))
    })
    try {
      check()
      return
    } catch (error) {
      lastError = error
    }
  }
  throw lastError
}

function buttonByText(container, text) {
  return [...container.querySelectorAll('button')].find((button) =>
    button.textContent.includes(text),
  )
}

afterEach(async () => {
  if (mountedView) await act(async () => { mountedView.unmount() })
  mountedView = undefined
  push.mockClear()
  session = { user: { isStaff: true } }
  graphqlCalls = []
  graphqlImpl = async () => ({})
  supported = false
  detector = null
  cameraResult = null
  cameraImpl = async () => cameraResult
  scanResult = null
  scanSignals = []
  stopCalls = []
  detectorCreateCalls = 0
  cameraStartCalls = 0
  frozenFrame = false
  captureCalls = []
  scanSearchParams = new URLSearchParams()
  vi.restoreAllMocks()
})

test('meal scanner shows the three most-used foods above a half-width camera', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = new Promise(() => {})
  graphqlImpl = async (operation) => operation.includes('MostUsedFoods')
    ? {
        mostUsedFoods: [
          { servingId: 's1', foodId: 'f1', name: 'Oats', brand: null, servingSize: 40, servingUnit: 'g', useCount: 8 },
          { servingId: 's2', foodId: 'f2', name: 'Yoghurt', brand: 'Farm', servingSize: 1, servingUnit: 'container', useCount: 6 },
          { servingId: 's3', foodId: 'f3', name: 'Rice', brand: null, servingSize: 100, servingUnit: 'g', useCount: 4 },
        ],
      }
    : {}

  const container = await mount()
  await settle(() => assert.match(container.textContent, /Your most-used foods/))
  assert.match(container.textContent, /Oats/)
  assert.match(container.textContent, /Farm Yoghurt/)
  assert.match(container.textContent, /Rice/)
  assert.ok(container.querySelector('[data-testid="camera-view"]').className.includes('w-1/2'))
  assert.ok(!container.querySelector('[data-testid="camera-panel"]').className.includes('w-1/2'))

  await act(async () => { buttonByText(container, 'Oats').click() })
  assert.equal(push.mock.calls[0][0], '/intakes/new?servingId=s1')
})

test('switching from product to intake mode reloads meal suggestions', async () => {
  scanSearchParams = new URLSearchParams([['mode', 'product']])
  const container = await mount()
  await settle(() => assert.match(container.textContent, /Camera barcode scanning is not available/))
  assert.equal(graphqlCalls.length, 0)

  scanSearchParams = new URLSearchParams([['mode', 'intake'], ['dayId', '7']])
  const { default: Page } = await import('../src/app/scan/page.tsx')
  await act(async () => { mountedView.rerender(React.createElement(Page)) })
  await settle(() => assert.match(container.textContent, /Your most-used foods/))
  assert.equal(graphqlCalls.length, 1)
})

test('product scanner shows only the camera workflow and does not load meal suggestions', async () => {
  scanSearchParams = new URLSearchParams([['mode', 'product']])
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = new Promise(() => {})

  const container = await mount()
  await settle(() => assert.match(container.textContent, /Point the camera at a product barcode/))

  assert.doesNotMatch(container.textContent, /Your most-used foods/)
  assert.equal(graphqlCalls.length, 0)
  assert.ok(container.querySelector('[data-testid="camera-view"]').className.includes('w-1/2'))
  assert.ok(!container.querySelector('[data-testid="camera-panel"]').className.includes('w-1/2'))
})

test('product scan results appear above the camera and keep existing products out of intake', async () => {
  scanSearchParams = new URLSearchParams([['mode', 'product']])
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: { id: 'p1', name: 'Oats', brand: null, size: 500, sizeUnit: 'g' },
      openFoodFacts: null,
    },
  })

  const container = await mount()
  await settle(() => assert.match(container.textContent, /Product already exists/))

  const result = container.querySelector('[data-testid="scan-result"]')
  const camera = container.querySelector('[data-testid="camera-panel"]')
  assert.ok(result.compareDocumentPosition(camera) & dom.window.Node.DOCUMENT_POSITION_FOLLOWING)
  assert.equal(push.mock.calls.length, 0)
})

test('product scanner labels an existing branded product', async () => {
  scanSearchParams = new URLSearchParams([['mode', 'product']])
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: { id: 'p1', name: 'Oats', brand: 'Farm', size: 500, sizeUnit: 'g' },
      openFoodFacts: null,
    },
  })

  const container = await mount()
  await settle(() => assert.match(container.textContent, /Farm Oats/))
})

test('product scanner returns Open Food Facts data to the product form without meal context', async () => {
  scanSearchParams = new URLSearchParams([['mode', 'product']])
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: null,
      openFoodFacts: {
        barcode: '3017620422003', brand: null, name: 'Oats', url: '',
        size: 500, sizeUnit: 'g', numServings: 5,
        nutritionalInfoSize: 100, nutritionalInfoUnit: 'g',
        energyKcal: 100, proteinG: 10, fatG: 2, carbsG: 12,
        saturatedFatG: null, sugarsG: null, fibreG: null, saltG: null,
      },
    },
  })

  const container = await mount()
  await settle(() => assert.ok(buttonByText(container, 'Create product from this data')))
  await act(async () => { buttonByText(container, 'Create product from this data').click() })

  const destination = push.mock.calls.at(-1)[0]
  assert.match(destination, /^\/products\/new\?/)
  assert.match(destination, /fromBarcodeScan=1/)
  assert.doesNotMatch(destination, /fromMealLog|intakeDayId/)
})

test('product scanner returns an unknown barcode to the product form without meal context', async () => {
  scanSearchParams = new URLSearchParams([['mode', 'product']])
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '123'
  graphqlImpl = async () => ({
    foodProductByBarcode: { product: null, openFoodFacts: null },
  })

  const container = await mount()
  await settle(() => assert.ok(buttonByText(container, 'Review and create product')))
  await act(async () => { buttonByText(container, 'Review and create product').click() })

  assert.equal(
    push.mock.calls.at(-1)[0],
    '/products/new?barcode=123&fromBarcodeScan=1',
  )
})

test('meal scanner ignores most-used foods that resolve after unmount', async () => {
  let resolveMostUsed
  graphqlImpl = async () => new Promise((resolve) => { resolveMostUsed = resolve })
  await mount()
  await settle(() => assert.equal(graphqlCalls.length, 1))
  await act(async () => { mountedView.unmount() })
  mountedView = undefined
  await act(async () => {
    resolveMostUsed({
      mostUsedFoods: [
        { servingId: 's1', foodId: 'f1', name: 'Late', brand: null, servingSize: 1, servingUnit: 'g', useCount: 1 },
      ],
    })
  })
  assert.equal(push.mock.calls.length, 0)
})

test('choosing a most-used food cancels a pending camera read and prevents later navigation', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  let resolveScan
  scanResult = new Promise((resolve) => { resolveScan = resolve })
  graphqlImpl = async (operation) => operation.includes('MostUsedFoods')
    ? { mostUsedFoods: [{ servingId: 's1', foodId: 'f1', name: 'Oats', brand: null, servingSize: 40, servingUnit: 'g', useCount: 8 }] }
    : { foodProductByBarcode: { product: { id: 'p1' }, openFoodFacts: null } }

  const container = await mount()
  await settle(() => assert.equal(scanSignals.length, 1))
  await act(async () => { buttonByText(container, 'Oats').click() })
  assert.equal(scanSignals[0].aborted, true)
  resolveScan('3017620422003')
  await act(async () => { await new Promise(setImmediate) })
  assert.deepEqual(push.mock.calls.map(([destination]) => destination), ['/intakes/new?servingId=s1'])
})

test('choosing a most-used food invalidates a pending manual lookup', async () => {
  let resolveLookup
  graphqlImpl = async (operation) => {
    if (operation.includes('MostUsedFoods')) {
      return { mostUsedFoods: [{ servingId: 's1', foodId: 'f1', name: 'Oats', brand: null, servingSize: 40, servingUnit: 'g', useCount: 8 }] }
    }
    return new Promise((resolve) => { resolveLookup = resolve })
  }

  const container = await mount()
  await act(async () => { buttonByText(container, 'Enter a barcode manually').click() })
  await act(async () => {
    fireEvent.change(container.querySelector('#barcode-input'), { target: { value: '123' } })
    fireEvent.submit(container.querySelector('form'))
  })
  await settle(() => assert.equal(typeof resolveLookup, 'function'))
  await act(async () => { buttonByText(container, 'Oats').click() })
  await act(async () => { buttonByText(container, 'Oats').click() })
  resolveLookup({ foodProductByBarcode: { product: { id: 'p1' }, openFoodFacts: null } })
  await act(async () => { await new Promise(setImmediate) })
  assert.deepEqual(push.mock.calls.map(([destination]) => destination), ['/intakes/new?servingId=s1'])
})

test('most-used food preserves an intake scanner day', async () => {
  scanSearchParams = new URLSearchParams([['mode', 'intake'], ['dayId', 'day 7']])
  graphqlImpl = async () => ({
    mostUsedFoods: [{ servingId: 's1', foodId: 'f1', name: 'Oats', brand: null, servingSize: 40, servingUnit: 'g', useCount: 8 }],
  })

  const container = await mount()
  await settle(() => assert.ok(buttonByText(container, 'Oats')))
  await act(async () => { buttonByText(container, 'Oats').click() })

  assert.equal(push.mock.calls[0][0], '/intakes/new?servingId=s1&dayId=day+7')
})

test('overlapping camera starts cannot orphan the newer stream', async () => {
  supported = true
  detector = {}
  const starts = []
  cameraImpl = async () => new Promise((resolve) => { starts.push(resolve) })
  scanResult = new Promise(() => {})

  await mount()
  await settle(() => assert.equal(starts.length, 1))
  scanSearchParams = new URLSearchParams([['mode', 'intake'], ['dayId', '7']])
  const { default: Page } = await import('../src/app/scan/page.tsx')
  await act(async () => { mountedView.rerender(React.createElement(Page)) })
  await settle(() => assert.equal(starts.length, 2))

  const newerStream = { getTracks: () => [] }
  const olderStream = { getTracks: () => [] }
  await act(async () => { starts[1](newerStream); await new Promise(setImmediate) })
  await act(async () => { starts[0](olderStream); await new Promise(setImmediate) })
  assert.deepEqual(stopCalls, [olderStream])

  await act(async () => { mountedView.unmount() })
  mountedView = undefined
  assert.deepEqual(stopCalls, [olderStream, newerStream])
})

test('meal scanner routes a detected local product to the intake form', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [{ stop: vi.fn() }] }
  scanResult = '3017620422003'
  graphqlImpl = async (operation) => operation.includes('MostUsedFoods')
    ? { mostUsedFoods: [] }
    : {
        foodProductByBarcode: {
          product: { id: 'p1', name: 'Oats', brand: null, size: 500, sizeUnit: 'g' },
          openFoodFacts: null,
        },
      }
  await mount()
  await settle(() => assert.equal(push.mock.calls.length, 1))
  assert.equal(push.mock.calls[0][0], '/intakes/new?productId=p1')
  assert.deepEqual(graphqlCalls.at(-1)[1], { barcode: '3017620422003' })
  assert.deepEqual(stopCalls, [cameraResult])
})

test('intake scan routes a local product directly to the intake form', async () => {
  scanSearchParams = new URLSearchParams([
    ['mode', 'intake'],
    ['dayId', 'day 7'],
  ])
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: { id: 'product/1', name: 'Oats', brand: null, size: 500, sizeUnit: 'g' },
      openFoodFacts: null,
    },
  })

  await mount()
  await settle(() => assert.equal(push.mock.calls.length, 1))
  assert.equal(
    push.mock.calls[0][0],
    '/intakes/new?dayId=day+7&productId=product%2F1',
  )
})

test('intake mode without a day still routes a local product to intake', async () => {
  scanSearchParams = new URLSearchParams([['mode', 'intake']])
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: { id: 'p1', name: 'Oats', brand: null, size: 500, sizeUnit: 'g' },
      openFoodFacts: null,
    },
  })

  await mount()
  await settle(() => assert.equal(push.mock.calls.length, 1))
  assert.equal(push.mock.calls[0][0], '/intakes/new?productId=p1')
})

test('scan page keeps the detected camera frame visible after stopping', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [{ stop: vi.fn() }] }
  scanResult = '3017620422003'
  frozenFrame = true
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: null,
      openFoodFacts: null,
    },
  })

  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /No product found/),
  )

  const canvas = container.querySelector('canvas[aria-label="Detected barcode frame"]')
  assert.ok(canvas)
  assert.doesNotMatch(canvas.className, /\bhidden\b/)
  assert.match(container.querySelector('video').className, /\bhidden\b/)
  assert.equal(captureCalls.length, 1)
  assert.equal(captureCalls[0][1], canvas)
})

test('scan page shows a lookup state after detecting a barcode', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  let resolveGraphql
  graphqlImpl = async () =>
    new Promise((resolve) => {
      resolveGraphql = resolve
    })
  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /Barcode detected. Looking up product/),
  )
  assert.doesNotMatch(
    container.textContent,
    /Camera barcode scanning is not available here/,
  )
  await act(async () => {
    resolveGraphql({
      foodProductByBarcode: { product: null, openFoodFacts: null },
    })
  })
  await settle(() =>
    assert.match(container.textContent, /No product found for barcode/),
  )
})

test('scan page ignores a pending intake lookup after unmount', async () => {
  scanSearchParams = new URLSearchParams([
    ['mode', 'intake'],
    ['dayId', '7'],
  ])
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  let resolveGraphql
  graphqlImpl = async () => new Promise((resolve) => { resolveGraphql = resolve })
  const container = await mount()
  await settle(() => assert.match(container.textContent, /Looking up product/))
  await act(async () => { mountedView.unmount() })
  mountedView = undefined
  await act(async () => {
    resolveGraphql({
      foodProductByBarcode: {
        product: { id: 'p1', name: 'Oats', brand: null, size: 500, sizeUnit: 'g' },
        openFoodFacts: null,
      },
    })
    await new Promise(setImmediate)
  })
  assert.equal(push.mock.calls.length, 0)

  let rejectGraphql
  graphqlImpl = async () => new Promise((_resolve, reject) => { rejectGraphql = reject })
  const nextContainer = await mount()
  await settle(() => assert.match(nextContainer.textContent, /Looking up product/))
  await act(async () => { mountedView.unmount() })
  mountedView = undefined
  await act(async () => {
    rejectGraphql(new Error('late lookup failure'))
    await new Promise(setImmediate)
  })
  assert.equal(push.mock.calls.length, 0)
})

test('scan page resets draft and pending manual state when intake context changes', async () => {
  scanSearchParams = new URLSearchParams([
    ['mode', 'intake'],
    ['dayId', '7'],
  ])
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: null,
      openFoodFacts: {
        barcode: '3017620422003', brand: null, name: 'Old draft', url: '',
        size: 100, sizeUnit: 'g', numServings: 1,
        nutritionalInfoSize: 100, nutritionalInfoUnit: 'g',
        energyKcal: 1, proteinG: 2, fatG: 3, carbsG: 4,
        saturatedFatG: null, sugarsG: null, fibreG: null, saltG: null,
      },
    },
  })
  const container = await mount()
  await settle(() => assert.match(container.textContent, /Old draft/))

  scanSearchParams = new URLSearchParams([
    ['mode', 'intake'],
    ['dayId', '8'],
  ])
  supported = false
  const { default: Page } = await import('../src/app/scan/page.tsx')
  await act(async () => { mountedView.rerender(React.createElement(Page)) })
  await settle(() => assert.match(container.textContent, /Camera barcode scanning is not available/))
  assert.doesNotMatch(container.textContent, /Old draft/)

  await act(async () => {
    buttonByText(container, 'Enter a barcode manually').click()
  })
  let resolveGraphql
  graphqlImpl = async () => new Promise((resolve) => { resolveGraphql = resolve })
  await act(async () => {
    fireEvent.change(container.querySelector('#barcode-input'), { target: { value: '123' } })
    fireEvent.submit(container.querySelector('form'))
  })
  await settle(() => assert.match(container.textContent, /Looking up/))

  scanSearchParams = new URLSearchParams([
    ['mode', 'intake'],
    ['dayId', '9'],
  ])
  await act(async () => { mountedView.rerender(React.createElement(Page)) })
  await settle(() => assert.match(container.textContent, /Camera barcode scanning is not available/))
  assert.doesNotMatch(container.textContent, /Looking up/)
  await act(async () => {
    resolveGraphql({
      foodProductByBarcode: {
        product: { id: 'p1', name: 'Oats', brand: null, size: 100, sizeUnit: 'g' },
        openFoodFacts: null,
      },
    })
    await new Promise(setImmediate)
  })
  assert.equal(push.mock.calls.length, 0)
})

test('scan page prefills the new product page from an OFF draft', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: null,
      openFoodFacts: {
        barcode: '3017620422003',
        brand: 'Ferrero',
        name: 'Nutella',
        url: 'https://world.openfoodfacts.org/product/3017620422003',
        size: 350,
        sizeUnit: 'g',
        numServings: 1,
        nutritionalInfoSize: 100,
        nutritionalInfoUnit: 'g',
        energyKcal: 539,
        proteinG: 6.3,
        fatG: 30.9,
        carbsG: 57.5,
        saturatedFatG: null,
        sugarsG: null,
        fibreG: null,
        saltG: 0.11,
      },
    },
  })
  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /Found on Open Food Facts/),
  )
  assert.match(container.textContent, /Nutella/)
  await act(async () => {
    buttonByText(container, 'Create product from this data').click()
  })
  assert.equal(
    push.mock.calls.at(-1)[0],
    '/products/new?barcode=3017620422003&brand=Ferrero&name=Nutella' +
      '&size=350&sizeUnit=g&numServings=1&nutritionalInfoSize=100' +
      '&nutritionalInfoUnit=g&energyKcal=539&proteinG=6.3&fatG=30.9' +
      '&carbsG=57.5&saltG=0.11&fromBarcodeScan=1&fromMealLog=1',
  )
})

test('intake scan preserves only its trusted day context for product creation', async () => {
  scanSearchParams = new URLSearchParams([
    ['mode', 'intake'],
    ['dayId', 'day 7'],
    ['returnTo', 'https://attacker.example/'],
  ])
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: null,
      openFoodFacts: {
        barcode: '3017620422003', brand: null, name: 'Oats', url: '',
        size: 500, sizeUnit: 'g', numServings: 5,
        nutritionalInfoSize: 100, nutritionalInfoUnit: 'g',
        energyKcal: 100, proteinG: 10, fatG: 2, carbsG: 12,
        saturatedFatG: null, sugarsG: null, fibreG: null, saltG: null,
      },
    },
  })

  const container = await mount()
  await settle(() => assert.match(container.textContent, /Found on Open Food Facts/))
  await act(async () => {
    buttonByText(container, 'Create product from this data').click()
  })
  const destination = push.mock.calls.at(-1)[0]
  assert.match(destination, /[?&]intakeDayId=day\+7(?:&|$)/)
  assert.doesNotMatch(destination, /returnTo|attacker/)
})

test('scan page warns when OFF nutrition is incomplete before review', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: null,
      openFoodFacts: {
        barcode: '3017620422003',
        brand: 'Unknown',
        name: 'Incomplete food',
        url: 'https://world.openfoodfacts.org/product/3017620422003',
        size: 100,
        sizeUnit: 'g',
        numServings: 1,
        nutritionalInfoSize: 100,
        nutritionalInfoUnit: 'g',
        energyKcal: null,
        proteinG: 2,
        fatG: 3,
        carbsG: 4,
        saturatedFatG: null,
        sugarsG: null,
        fibreG: null,
        saltG: null,
      },
    },
  })
  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /Product data is incomplete/),
  )
  await act(async () => {
    buttonByText(container, 'Review and complete product data').click()
  })
  const destination = push.mock.calls.at(-1)[0]
  assert.match(destination, /proteinG=2/)
  assert.doesNotMatch(destination, /energyKcal=/)
  assert.match(destination, /fromBarcodeScan=1/)
})

test('scan page requires review when OFF package quantity is unknown', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: null,
      openFoodFacts: {
        barcode: '3017620422003', brand: null, name: 'Multipack', url: '',
        size: null, sizeUnit: null, numServings: 1,
        nutritionalInfoSize: 100, nutritionalInfoUnit: 'g',
        energyKcal: 1, proteinG: 2, fatG: 3, carbsG: 4,
        saturatedFatG: null, sugarsG: null, fibreG: null, saltG: null,
      },
    },
  })
  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /Product data is incomplete/),
  )
  await act(async () => {
    buttonByText(container, 'Review and complete product data').click()
  })
  const destination = push.mock.calls.at(-1)[0]
  assert.doesNotMatch(destination, /[?&]size=/)
  assert.match(destination, /fromBarcodeScan=1/)
})

test('scan page requires review when OFF package unit is unknown', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: null,
      openFoodFacts: {
        barcode: '3017620422003', brand: null, name: 'Unknown unit', url: '',
        size: 100, sizeUnit: null, numServings: 1,
        nutritionalInfoSize: 100, nutritionalInfoUnit: 'g',
        energyKcal: 1, proteinG: 2, fatG: 3, carbsG: 4,
        saturatedFatG: null, sugarsG: null, fibreG: null, saltG: null,
      },
    },
  })
  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /Product data is incomplete/),
  )
})

test('scan page does not offer staff-only product creation to regular users', async () => {
  session = { user: { isStaff: false } }
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '3017620422003'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: null,
      openFoodFacts: {
        barcode: '3017620422003', brand: null, name: 'Found food', url: '',
        size: 100, sizeUnit: 'g', numServings: 1,
        nutritionalInfoSize: 100, nutritionalInfoUnit: 'g',
        energyKcal: 1, proteinG: 2, fatG: 3, carbsG: 4,
        saturatedFatG: null, sugarsG: null, fibreG: null, saltG: null,
      },
    },
  })
  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /A staff user must review and create/),
  )
  assert.equal(buttonByText(container, 'Create product from this data'), undefined)
})

test('scan page reports unknown barcodes', async () => {
  scanSearchParams = new URLSearchParams([
    ['mode', 'intake'],
    ['dayId', 'day 7'],
  ])
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '123'
  graphqlImpl = async () => ({
    foodProductByBarcode: { product: null, openFoodFacts: null },
  })
  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /No product found for barcode 123/),
  )
  await act(async () => {
    buttonByText(container, 'Review and create product').click()
  })
  assert.equal(
    push.mock.calls.at(-1)[0],
    '/products/new?barcode=123&fromBarcodeScan=1&fromMealLog=1&intakeDayId=day+7',
  )
})

test('unknown meal-scan barcodes open creation with meal continuation', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '123'
  graphqlImpl = async () => ({
    foodProductByBarcode: { product: null, openFoodFacts: null },
  })
  const container = await mount()
  await settle(() => assert.match(container.textContent, /No product found/))
  await act(async () => {
    buttonByText(container, 'Review and create product').click()
  })
  assert.equal(
    push.mock.calls.at(-1)[0],
    '/products/new?barcode=123&fromBarcodeScan=1&fromMealLog=1',
  )
})

test('unknown barcodes keep manual creation staff-only', async () => {
  session = { user: { isStaff: false } }
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '123'
  graphqlImpl = async () => ({
    foodProductByBarcode: { product: null, openFoodFacts: null },
  })
  const container = await mount()
  await settle(() => assert.match(
    container.textContent,
    /A staff user must review and create this product/,
  ))
  assert.equal(buttonByText(container, 'Review and create product'), undefined)
})

test('scan page shows lookup error messages', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '123'
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  graphqlImpl = async () => {
    throw new Error('network down')
  }
  const container = await mount()
  await settle(() => assert.match(container.textContent, /network down/))
  assert.ok(container.querySelector('[role="alert"]'))
  assert.match(consoleError.mock.calls[0][0], /Failed to fetch most-used foods/)
})

test('scan page falls back to a generic message for non-Error failures', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '123'
  graphqlImpl = async (operation) => {
    if (operation.includes('MostUsedFoods')) return { mostUsedFoods: [] }
    throw 'boom'
  }
  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /Barcode lookup failed/),
  )
})

test('scan page offers manual entry when the camera is unsupported', async () => {
  supported = false
  const container = await mount()
  await settle(() =>
    assert.match(
      container.textContent,
      /Camera barcode scanning is not available here/,
    ),
  )
  await act(async () => {
    buttonByText(container, 'Enter a barcode manually').click()
  })
  assert.ok(container.querySelector('#barcode-input'))
})

test('scan page falls back when the detector cannot be created', async () => {
  supported = true
  detector = null
  const container = await mount()
  await settle(() =>
    assert.match(
      container.textContent,
      /Camera barcode scanning is not available here/,
    ),
  )
})

test('scan page falls back when the camera stream cannot start', async () => {
  supported = true
  detector = {}
  cameraResult = null
  const container = await mount()
  await settle(() =>
    assert.match(
      container.textContent,
      /Camera barcode scanning is not available here/,
    ),
  )
})

test('scan page stops the camera when no barcode is detected', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = null
  const container = await mount()
  await settle(() =>
    assert.match(
      container.textContent,
      /Camera barcode scanning is not available here/,
    ),
  )
  assert.deepEqual(stopCalls, [cameraResult])
})

test('scan page switches to manual entry from the camera view', async () => {
  supported = true
  detector = {}
  let resolveCamera
  cameraResult = new Promise((resolve) => {
    resolveCamera = resolve
  })
  const container = await mount()
  await act(async () => {})
  await act(async () => {
    buttonByText(container, 'Type barcode instead').click()
  })
  assert.ok(container.querySelector('#barcode-input'))
  const stream = { getTracks: () => [] }
  await act(async () => {
    resolveCamera(stream)
  })
  assert.deepEqual(stopCalls, [stream])
})

test('scan page stops an active scan when switching to manual entry', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  let resolveScan
  scanResult = new Promise((resolve) => {
    resolveScan = resolve
  })
  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /Point the camera at a product barcode/),
  )
  await act(async () => {
    buttonByText(container, 'Type barcode instead').click()
  })
  assert.ok(container.querySelector('#barcode-input'))
  assert.equal(scanSignals.at(-1).aborted, true)
  assert.deepEqual(stopCalls, [cameraResult])
  await act(async () => {
    resolveScan('3017620422003')
  })
  assert.equal(graphqlCalls.length, 1)
})

test('scan page looks up manually entered barcodes', async () => {
  supported = false
  const container = await mount()
  await settle(() =>
    assert.match(
      container.textContent,
      /Camera barcode scanning is not available here/,
    ),
  )
  await act(async () => {
    buttonByText(container, 'Enter a barcode manually').click()
  })
  fireEvent.change(container.querySelector('#barcode-input'), {
    target: { value: '3017620422003' },
  })
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: { id: 'p9', name: 'Manual', brand: null, size: 1, sizeUnit: 'g' },
      openFoodFacts: null,
    },
  })
  await act(async () => {
    fireEvent.submit(container.querySelector('form'))
  })
  await settle(() => assert.equal(push.mock.calls.length, 1))
  assert.equal(push.mock.calls[0][0], '/intakes/new?productId=p9')
  assert.deepEqual(graphqlCalls.at(-1)[1], { barcode: '3017620422003' })
})

test('scan page ignores empty manual submissions', async () => {
  supported = false
  const container = await mount()
  await settle(() =>
    assert.match(
      container.textContent,
      /Camera barcode scanning is not available here/,
    ),
  )
  await act(async () => {
    buttonByText(container, 'Enter a barcode manually').click()
  })
  await act(async () => {
    fireEvent.submit(container.querySelector('form'))
  })
  assert.equal(graphqlCalls.length, 1)
})

test('scan page disables manual lookup while searching', async () => {
  supported = false
  const container = await mount()
  await settle(() =>
    assert.match(
      container.textContent,
      /Camera barcode scanning is not available here/,
    ),
  )
  await act(async () => {
    buttonByText(container, 'Enter a barcode manually').click()
  })
  fireEvent.change(container.querySelector('#barcode-input'), {
    target: { value: '3017620422003' },
  })
  let resolveGraphql
  graphqlImpl = async () =>
    new Promise((resolve) => {
      resolveGraphql = resolve
    })
  await act(async () => {
    fireEvent.submit(container.querySelector('form'))
  })
  const submitButton = buttonByText(container, 'Looking up')
  assert.ok(submitButton)
  assert.equal(submitButton.disabled, true)
  await act(async () => {
    resolveGraphql({
      foodProductByBarcode: {
        product: { id: 'p1', name: 'A', brand: null, size: 1, sizeUnit: 'g' },
        openFoodFacts: null,
      },
    })
  })
  await settle(() => assert.equal(push.mock.calls.length, 1))
  assert.equal(push.mock.calls[0][0], '/intakes/new?productId=p1')
})

test('scan page restarts the camera after a result', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  scanResult = '123'
  graphqlImpl = async () => ({
    foodProductByBarcode: {
      product: null,
      openFoodFacts: null,
    },
  })
  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /No product found/),
  )
  assert.equal(graphqlCalls.length, 2)
  await act(async () => {
    buttonByText(container, 'Scan another').click()
  })
  await settle(() => assert.equal(graphqlCalls.length, 3))
  assert.deepEqual(graphqlCalls.at(-1)[1], { barcode: '123' })
})

test('scan page stops the camera stream when unmounted mid-start', async () => {
  supported = true
  detector = {}
  let resolveCamera
  cameraResult = new Promise((resolve) => {
    resolveCamera = resolve
  })
  await mount()
  await act(async () => {})
  await act(async () => {
    mountedView.unmount()
  })
  mountedView = undefined
  const stream = { getTracks: () => [] }
  await act(async () => {
    resolveCamera(stream)
  })
  assert.ok(stopCalls.includes(stream))
})

test('scan page does not acquire a camera after detector startup is cancelled', async () => {
  supported = true
  let resolveDetector
  detector = new Promise((resolve) => {
    resolveDetector = resolve
  })
  await mount()
  await settle(() => assert.equal(detectorCreateCalls, 1))
  await act(async () => {
    mountedView.unmount()
  })
  mountedView = undefined
  await act(async () => {
    resolveDetector({})
  })
  assert.equal(cameraStartCalls, 0)
})

test('scan page stops the camera stream when unmounted mid-scan', async () => {
  supported = true
  detector = {}
  cameraResult = { getTracks: () => [] }
  let resolveScan
  scanResult = new Promise((resolve) => {
    resolveScan = resolve
  })
  const container = await mount()
  await settle(() =>
    assert.match(container.textContent, /Point the camera at a product barcode/),
  )
  await act(async () => {
    mountedView.unmount()
  })
  mountedView = undefined
  assert.ok(stopCalls.includes(cameraResult))
  await act(async () => {
    resolveScan('3017620422003')
  })
  assert.equal(graphqlCalls.length, 1)
})
