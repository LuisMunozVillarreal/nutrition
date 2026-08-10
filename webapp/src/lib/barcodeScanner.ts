export interface DetectedBarcode {
  rawValue: string
}

export interface BarcodeDetectorLike {
  detect(source: unknown): Promise<DetectedBarcode[]>
}

interface DetectorConstructor {
  new (options?: { formats?: string[] }): BarcodeDetectorLike
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
    return new Constructor()
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
  try {
    const stream = await mediaDevices.getUserMedia({
      video: { facingMode: 'environment' },
      audio: false,
    })
    video.srcObject = stream
    await video.play()
    return stream
  } catch {
    return null
  }
}

export function stopCameraStream(stream: MediaStream | null): void {
  if (!stream) return
  for (const track of stream.getTracks()) {
    track.stop()
  }
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
    for (const code of codes) {
      if (code.rawValue) return code.rawValue
    }
  }
  return null
}
