export interface DetectedBarcode {
  rawValue: string
  format?: string
}

export interface BarcodeDetectorLike {
  detect(source: unknown): Promise<DetectedBarcode[]>
}

interface DetectorConstructor {
  new (options?: { formats?: string[] }): BarcodeDetectorLike
}

const PRODUCT_BARCODE_FORMATS = ['ean_13', 'ean_8', 'upc_a', 'upc_e']

interface OptionalVideoFrameCallbacks {
  requestVideoFrameCallback?: (callback: () => void) => number
  cancelVideoFrameCallback?: (handle: number) => void
}

export function expandUpcE(rawValue: string): string | null {
  if (!/^[01]\d{7}$/.test(rawValue)) return null
  const [numberSystem, first, second, third, fourth, fifth, sixth, check] =
    rawValue
  let payload: string
  if ('012'.includes(sixth)) {
    payload = `${numberSystem}${first}${second}${sixth}0000${third}${fourth}${fifth}`
  } else if (sixth === '3') {
    payload = `${numberSystem}${first}${second}${third}00000${fourth}${fifth}`
  } else if (sixth === '4') {
    payload = `${numberSystem}${first}${second}${third}${fourth}00000${fifth}`
  } else {
    payload = `${numberSystem}${first}${second}${third}${fourth}${fifth}0000${sixth}`
  }
  return `${payload}${check}`
}

export function isBarcodeDetectorSupported(): boolean {
  if (typeof window === 'undefined') return false
  return (
    typeof (window as { BarcodeDetector?: unknown }).BarcodeDetector ===
    'function'
  )
}

export async function createBarcodeDetector(): Promise<BarcodeDetectorLike | null> {
  if (!isBarcodeDetectorSupported()) return null
  try {
    const Constructor = (
      window as unknown as { BarcodeDetector: DetectorConstructor }
    ).BarcodeDetector
    return new Constructor({ formats: PRODUCT_BARCODE_FORMATS })
  } catch {
    return null
  }
}

export async function startCameraStream(
  video: HTMLVideoElement,
): Promise<MediaStream | null> {
  const mediaDevices =
    typeof navigator === 'undefined' ? undefined : navigator.mediaDevices
  if (!mediaDevices?.getUserMedia) return null
  let stream: MediaStream | null = null
  try {
    stream = await mediaDevices.getUserMedia({
      video: { facingMode: 'environment' },
      audio: false,
    })
    video.srcObject = stream
    await video.play()
    return stream
  } catch {
    stopCameraStream(stream)
    video.srcObject = null
    return null
  }
}

export function stopCameraStream(stream: MediaStream | null): void {
  if (!stream) return
  for (const track of stream.getTracks()) {
    track.stop()
  }
}

export function captureVideoFrame(
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
): boolean {
  if (!video.videoWidth || !video.videoHeight) return false
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  const context = canvas.getContext('2d')
  if (!context) return false
  try {
    context.drawImage(video, 0, 0, canvas.width, canvas.height)
    return true
  } catch {
    return false
  }
}

function waitForNextFrame(
  video: HTMLVideoElement,
  signal?: AbortSignal,
): Promise<void> {
  const frameVideo = video as unknown as OptionalVideoFrameCallbacks
  return new Promise((resolve) => {
    let handle: number
    let cancelFrame: (frameHandle: number) => void
    const finish = () => {
      signal?.removeEventListener('abort', abort)
      resolve()
    }
    const abort = () => {
      cancelFrame(handle)
      finish()
    }
    signal?.addEventListener('abort', abort, { once: true })
    if (
      frameVideo.requestVideoFrameCallback &&
      frameVideo.cancelVideoFrameCallback
    ) {
      cancelFrame = frameVideo.cancelVideoFrameCallback.bind(video)
      handle = frameVideo.requestVideoFrameCallback.bind(video)(finish)
    } else {
      cancelFrame = cancelAnimationFrame
      handle = requestAnimationFrame(finish)
    }
  })
}

export async function readBarcodeFromVideo(
  video: HTMLVideoElement,
  detector: BarcodeDetectorLike,
  signal?: AbortSignal,
): Promise<string | null> {
  while (!signal?.aborted) {
    let codes: DetectedBarcode[]
    try {
      codes = await detector.detect(video)
    } catch {
      return null
    }
    if (signal?.aborted) return null
    for (const code of codes) {
      if (!code.rawValue) continue
      if (code.format !== 'upc_e') return code.rawValue
      const expanded = expandUpcE(code.rawValue)
      if (expanded) return expanded
    }
    await waitForNextFrame(video, signal)
  }
  return null
}
