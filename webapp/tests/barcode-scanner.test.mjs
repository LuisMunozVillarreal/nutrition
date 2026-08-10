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
  vi.unstubAllGlobals()
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
  let options
  dom.window.BarcodeDetector = class FakeDetector {
    constructor(detectorOptions) {
      options = detectorOptions
    }
  }
  const detector = await scanner.createBarcodeDetector()
  assert.ok(detector instanceof dom.window.BarcodeDetector)
  assert.deepEqual(options, {
    formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e'],
  })
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

test('startCameraStream stops an acquired stream when video playback fails', async () => {
  const stop = vi.fn()
  const stream = { getTracks: () => [{ stop }] }
  const video = {
    srcObject: null,
    play: vi.fn(async () => {
      throw new Error('playback failed')
    }),
  }
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      mediaDevices: {
        getUserMedia: async () => stream,
      },
    },
  })
  assert.equal(await scanner.startCameraStream(video), null)
  assert.equal(stop.mock.calls.length, 1)
  assert.equal(video.srcObject, null)
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

test('expandUpcE expands every UPC-E compression form', () => {
  assert.equal(scanner.expandUpcE('04252614'), '042100005264')
  assert.equal(scanner.expandUpcE('01234505'), '012000003455')
  assert.equal(scanner.expandUpcE('01234535'), '012300000455')
  assert.equal(scanner.expandUpcE('01234545'), '012340000055')
  assert.equal(scanner.expandUpcE('01234565'), '012345000065')
  assert.equal(scanner.expandUpcE('21234565'), null)
  assert.equal(scanner.expandUpcE('0123456x'), null)
})

test('readBarcodeFromVideo keeps scanning until a later frame contains a code', async () => {
  vi.stubGlobal('requestAnimationFrame', (callback) =>
    setTimeout(() => callback(0), 0),
  )
  vi.stubGlobal('cancelAnimationFrame', (handle) => clearTimeout(handle))
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

test('readBarcodeFromVideo returns null when scanning is externally cancelled', async () => {
  vi.stubGlobal('requestAnimationFrame', (callback) =>
    setTimeout(() => callback(0), 50),
  )
  vi.stubGlobal('cancelAnimationFrame', (handle) => clearTimeout(handle))
  const controller = new AbortController()
  let calls = 0
  let firstDetection
  const firstDetectionStarted = new Promise((resolve) => {
    firstDetection = resolve
  })
  const detector = {
    detect: async () => {
      calls += 1
      firstDetection()
      return []
    },
  }
  const scan = scanner.readBarcodeFromVideo({}, detector, controller.signal)
  await firstDetectionStarted
  controller.abort()
  assert.equal(await scan, null)
  assert.equal(calls, 1)
})

test('readBarcodeFromVideo prefers a newly presented video frame', async () => {
  let nextVideoFrame
  const requestVideoFrameCallback = vi.fn((callback) => {
    nextVideoFrame = callback
    return 17
  })
  const cancelVideoFrameCallback = vi.fn()
  let calls = 0
  const detector = {
    detect: async () => {
      calls += 1
      return calls === 1 ? [] : [{ rawValue: '3017620422003' }]
    },
  }
  const scan = scanner.readBarcodeFromVideo(
    { requestVideoFrameCallback, cancelVideoFrameCallback },
    detector,
  )
  await vi.waitFor(() => {
    assert.equal(requestVideoFrameCallback.mock.calls.length, 1)
  })
  nextVideoFrame()
  assert.equal(await scan, '3017620422003')
  assert.equal(calls, 2)
  assert.equal(cancelVideoFrameCallback.mock.calls.length, 0)
})

test('readBarcodeFromVideo cancels a pending video-frame callback', async () => {
  const requestVideoFrameCallback = vi.fn(() => 23)
  const cancelVideoFrameCallback = vi.fn()
  const controller = new AbortController()
  const detector = { detect: async () => [] }
  const scan = scanner.readBarcodeFromVideo(
    { requestVideoFrameCallback, cancelVideoFrameCallback },
    detector,
    controller.signal,
  )
  await vi.waitFor(() => {
    assert.equal(requestVideoFrameCallback.mock.calls.length, 1)
  })
  controller.abort()
  assert.equal(await scan, null)
  assert.deepEqual(cancelVideoFrameCallback.mock.calls, [[23]])
})

test('readBarcodeFromVideo resolves when aborted during detection', async () => {
  let finishDetection
  const detection = new Promise((resolve) => {
    finishDetection = resolve
  })
  const requestAnimationFrame = vi.fn()
  vi.stubGlobal('requestAnimationFrame', requestAnimationFrame)
  const controller = new AbortController()
  const scan = scanner.readBarcodeFromVideo(
    {},
    { detect: () => detection },
    controller.signal,
  )
  controller.abort()
  finishDetection([])
  assert.equal(await scan, null)
  assert.equal(requestAnimationFrame.mock.calls.length, 0)
})

test('readBarcodeFromVideo expands a detected UPC-E barcode', async () => {
  const detector = {
    detect: async () => [{ rawValue: '04252614', format: 'upc_e' }],
  }
  assert.equal(
    await scanner.readBarcodeFromVideo({}, detector),
    '042100005264',
  )
})

test('readBarcodeFromVideo ignores malformed UPC-E detections', async () => {
  vi.stubGlobal('requestAnimationFrame', (callback) =>
    setTimeout(() => callback(0), 0),
  )
  vi.stubGlobal('cancelAnimationFrame', (handle) => clearTimeout(handle))
  let calls = 0
  const detector = {
    detect: async () => {
      calls += 1
      return calls === 1
        ? [{ rawValue: 'invalid', format: 'upc_e' }]
        : [{ rawValue: '3017620422003', format: 'ean_13' }]
    },
  }
  assert.equal(
    await scanner.readBarcodeFromVideo({}, detector),
    '3017620422003',
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
