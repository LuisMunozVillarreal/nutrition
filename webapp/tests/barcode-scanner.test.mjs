import assert from 'node:assert/strict'
import { afterEach, test, vi } from 'vitest'
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://example.com/',
})

const originalWindow = globalThis.window
const originalNavigator = globalThis.navigator

const scanner = await import('../src/lib/barcodeScanner.ts')

afterEach(() => {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: originalWindow,
  })
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: originalNavigator,
  })
})

test('barcode detector support reflects the window capability', () => {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: dom.window,
  })
  assert.equal(scanner.isBarcodeDetectorSupported(), false)
  dom.window.BarcodeDetector = class FakeDetector {}
  assert.equal(scanner.isBarcodeDetectorSupported(), true)
  delete dom.window.BarcodeDetector
})

test('barcode detector support is false without a window', () => {
  delete globalThis.window
  assert.equal(scanner.isBarcodeDetectorSupported(), false)
})

test('createBarcodeDetector returns null without support', async () => {
  assert.equal(await scanner.createBarcodeDetector(), null)
})

test('createBarcodeDetector returns an instance when supported', async () => {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: dom.window,
  })
  dom.window.BarcodeDetector = class FakeDetector {}
  const detector = await scanner.createBarcodeDetector()
  assert.ok(detector instanceof dom.window.BarcodeDetector)
  delete dom.window.BarcodeDetector
})

test('createBarcodeDetector returns null when construction fails', async () => {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: dom.window,
  })
  dom.window.BarcodeDetector = class ThrowingDetector {
    constructor() {
      throw new Error('formats unavailable')
    }
  }
  assert.equal(await scanner.createBarcodeDetector(), null)
  delete dom.window.BarcodeDetector
})

test('startCameraStream returns null without a navigator', async () => {
  const video = { srcObject: null, play: vi.fn() }
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: undefined,
  })
  assert.equal(await scanner.startCameraStream(video), null)
})

test('startCameraStream returns null without mediaDevices', async () => {
  const video = { srcObject: null, play: vi.fn() }
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: { mediaDevices: undefined },
  })
  assert.equal(await scanner.startCameraStream(video), null)
})

test('startCameraStream returns null when the camera is denied', async () => {
  const video = { srcObject: null, play: vi.fn() }
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      mediaDevices: {
        getUserMedia: async () => {
          throw new Error('permission denied')
        },
      },
    },
  })
  assert.equal(await scanner.startCameraStream(video), null)
})

test('startCameraStream attaches the stream and plays the video', async () => {
  const stream = { getTracks: () => [] }
  const video = { srcObject: null, play: vi.fn(async () => {}) }
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      mediaDevices: {
        getUserMedia: async () => stream,
      },
    },
  })
  const result = await scanner.startCameraStream(video)
  assert.equal(result, stream)
  assert.equal(video.srcObject, stream)
  assert.equal(video.play.mock.calls.length, 1)
})

test('stopCameraStream stops every track', () => {
  const firstStop = vi.fn()
  const secondStop = vi.fn()
  scanner.stopCameraStream({
    getTracks: () => [{ stop: firstStop }, { stop: secondStop }],
  })
  assert.equal(firstStop.mock.calls.length, 1)
  assert.equal(secondStop.mock.calls.length, 1)
})

test('stopCameraStream tolerates a null stream', () => {
  scanner.stopCameraStream(null)
})

test('readBarcodeFromVideo keeps scanning until a later frame contains a code', async () => {
  let calls = 0
  const detector = {
    detect: async () => {
      calls += 1
      if (calls === 1) return []
      return [
        { rawValue: '' },
        { rawValue: '3017620422003' },
        { rawValue: '999' },
      ]
    },
  }
  assert.equal(
    await scanner.readBarcodeFromVideo({}, detector),
    '3017620422003',
  )
  assert.equal(calls, 2)
})

test('readBarcodeFromVideo returns null when scanning is cancelled', async () => {
  const controller = new AbortController()
  const detector = {
    detect: async () => {
      controller.abort()
      return []
    },
  }
  assert.equal(
    await scanner.readBarcodeFromVideo({}, detector, controller.signal),
    null,
  )
})

test('readBarcodeFromVideo returns null when detection throws', async () => {
  const detector = {
    detect: async () => {
      throw new Error('detection failed')
    },
  }
  assert.equal(await scanner.readBarcodeFromVideo({}, detector), null)
})
