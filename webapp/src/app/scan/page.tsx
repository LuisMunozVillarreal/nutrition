'use client'

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { graphqlRequest, gql } from '@/lib/graphql'
import {
  captureVideoFrame,
  createBarcodeDetector,
  isBarcodeDetectorSupported,
  readBarcodeFromVideo,
  startCameraStream,
  stopCameraStream,
} from '@/lib/barcodeScanner'

const LOOKUP_QUERY = gql`
  query FoodProductByBarcode($barcode: String!) {
    foodProductByBarcode(barcode: $barcode) {
      product { id name brand size sizeUnit }
      openFoodFacts {
        barcode brand name url size sizeUnit numServings
        nutritionalInfoSize nutritionalInfoUnit
        energyKcal proteinG fatG carbsG saturatedFatG sugarsG fibreG saltG
      }
    }
  }
`

interface LocalProduct {
  id: string
  name: string
  brand: string | null
  size: number
  sizeUnit: string
}

export interface OpenFoodFactsDraft {
  barcode: string
  brand: string | null
  name: string
  url: string
  size: number | null
  sizeUnit: string | null
  numServings: number
  nutritionalInfoSize: number
  nutritionalInfoUnit: string
  energyKcal: number | null
  proteinG: number | null
  fatG: number | null
  carbsG: number | null
  saturatedFatG: number | null
  sugarsG: number | null
  fibreG: number | null
  saltG: number | null
}

interface BarcodeLookupResult {
  foodProductByBarcode: {
    product: LocalProduct | null
    openFoodFacts: OpenFoodFactsDraft | null
  }
}

type CameraState = 'starting' | 'active' | 'stopped' | 'unavailable'

const DRAFT_QUERY_FIELDS: Array<keyof OpenFoodFactsDraft> = [
  'barcode',
  'brand',
  'name',
  'size',
  'sizeUnit',
  'numServings',
  'nutritionalInfoSize',
  'nutritionalInfoUnit',
  'energyKcal',
  'proteinG',
  'fatG',
  'carbsG',
  'saturatedFatG',
  'sugarsG',
  'fibreG',
  'saltG',
]

const REQUIRED_NUTRIENTS: Array<
  'energyKcal' | 'proteinG' | 'fatG' | 'carbsG'
> = ['energyKcal', 'proteinG', 'fatG', 'carbsG']

export default function ScanPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const requestedDayId = searchParams.get('dayId')?.trim()
  const intakeDayId = searchParams.get('mode') === 'intake' && requestedDayId
    ? requestedDayId
    : null
  const { data: session } = useSession()
  const isStaff = session?.user?.isStaff === true
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const lookupGenerationRef = useRef(0)
  const [frameCaptured, setFrameCaptured] = useState(false)
  const [cameraState, setCameraState] = useState<CameraState>('starting')
  const [manual, setManual] = useState(false)
  const [barcodeInput, setBarcodeInput] = useState('')
  const [searching, setSearching] = useState(false)
  const [lookup, setLookup] = useState<{
    barcode: string
    result: BarcodeLookupResult['foodProductByBarcode']
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [scanKey, setScanKey] = useState(0)

  const searchBarcode = useCallback(async (barcode: string) => {
    const generation = ++lookupGenerationRef.current
    setSearching(true)
    setError(null)
    try {
      const res = await graphqlRequest<BarcodeLookupResult>(LOOKUP_QUERY, {
        barcode,
      })
      if (generation !== lookupGenerationRef.current) return
      const result = res.foodProductByBarcode
      if (intakeDayId && result.product) {
        const params = new URLSearchParams({
          dayId: intakeDayId,
          productId: result.product.id,
        })
        router.push(`/intakes/new?${params.toString()}`)
        return
      }
      setLookup({ barcode, result })
    } catch (err) {
      if (generation !== lookupGenerationRef.current) return
      setLookup(null)
      setError(
        err instanceof Error ? err.message : 'Barcode lookup failed',
      )
    } finally {
      if (generation === lookupGenerationRef.current) setSearching(false)
    }
  }, [intakeDayId, router])

  useEffect(() => () => {
    lookupGenerationRef.current += 1
  }, [intakeDayId])

  useEffect(() => {
    if (manual) return
    let cancelled = false
    let activeStream: MediaStream | null = null
    const scanController = new AbortController()
    // The video element is mounted whenever this effect runs: the initial
    // state renders it, and restart() re-renders it before bumping scanKey.
    const video = videoRef.current!

    const start = async () => {
      if (!isBarcodeDetectorSupported()) {
        setCameraState('unavailable')
        return
      }
      const detector = await createBarcodeDetector()
      if (cancelled || scanController.signal.aborted) return
      if (!detector) {
        setCameraState('unavailable')
        return
      }
      const stream = await startCameraStream(video)
      if (!stream) {
        setCameraState('unavailable')
        return
      }
      activeStream = stream
      if (cancelled) {
        stopCameraStream(stream)
        return
      }
      setCameraState('active')
      const value = await readBarcodeFromVideo(
        video,
        detector,
        scanController.signal,
      )
      if (cancelled) return
      if (!value) {
        stopCameraStream(stream)
        activeStream = null
        setCameraState('unavailable')
        return
      }
      const canvas = canvasRef.current!
      setFrameCaptured(captureVideoFrame(video, canvas))
      stopCameraStream(stream)
      activeStream = null
      setCameraState('stopped')
      searchBarcode(value)
    }

    void start()

    return () => {
      cancelled = true
      scanController.abort()
      if (activeStream) stopCameraStream(activeStream)
    }
  }, [manual, scanKey, searchBarcode])

  const handleManualSubmit = (event: FormEvent) => {
    event.preventDefault()
    const barcode = barcodeInput.trim()
    if (!barcode) return
    searchBarcode(barcode)
  }

  const createFromDraft = useCallback(
    (draft: OpenFoodFactsDraft) => {
      const params = new URLSearchParams()
      for (const field of DRAFT_QUERY_FIELDS) {
        const value = draft[field]
        if (value !== null && value !== undefined) {
          params.set(field, String(value))
        }
      }
      params.set('fromBarcodeScan', '1')
      if (intakeDayId) params.set('intakeDayId', intakeDayId)
      router.push(`/products/new?${params.toString()}`)
    },
    [intakeDayId, router],
  )

  const createFromBarcode = useCallback((barcode: string) => {
    const params = new URLSearchParams({
      barcode,
      fromBarcodeScan: '1',
    })
    if (intakeDayId) params.set('intakeDayId', intakeDayId)
    router.push(`/products/new?${params.toString()}`)
  }, [intakeDayId, router])

  const restart = () => {
    lookupGenerationRef.current += 1
    setLookup(null)
    setError(null)
    setManual(false)
    setFrameCaptured(false)
    setCameraState('starting')
    setScanKey((key) => key + 1)
  }

  const draft = lookup?.result.openFoodFacts
  const draftIsComplete =
    draft !== null &&
    draft !== undefined &&
    draft.size !== null &&
    draft.sizeUnit !== null &&
    REQUIRED_NUTRIENTS.every((field) => draft[field] !== null)

  return (
    <div className="max-w-4xl">
      <h1 className="page-title mb-6">Scan Barcode</h1>

      {!manual && cameraState !== 'unavailable' && (
        <div className="space-y-4">
          <video
            ref={videoRef}
            className={`aspect-[3/4] w-full rounded-lg bg-slate-900 object-cover sm:aspect-video ${frameCaptured ? 'hidden' : ''}`}
            muted
            playsInline
          />
          <canvas
            ref={canvasRef}
            aria-label="Detected barcode frame"
            className={`aspect-[3/4] w-full rounded-lg bg-slate-900 object-cover sm:aspect-video ${frameCaptured ? '' : 'hidden'}`}
          />
          {cameraState === 'starting' && (
            <p className="text-slate-500">Starting camera...</p>
          )}
          {cameraState === 'active' && (
            <p className="text-slate-500">
              Point the camera at a product barcode.
            </p>
          )}
          <button
            type="button"
            onClick={() => setManual(true)}
            className="text-slate-600 underline"
          >
            Type barcode instead
          </button>
        </div>
      )}

      {manual && (
        <form onSubmit={handleManualSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="barcode-input"
              className="mb-1 block text-sm font-medium text-slate-700"
            >
              Barcode
            </label>
            <input
              id="barcode-input"
              value={barcodeInput}
              onChange={(event) => setBarcodeInput(event.target.value)}
              placeholder="e.g. 3017620422003"
              className="w-full rounded-lg border border-slate-300 px-3 py-2"
            />
          </div>
          <button
            type="submit"
            disabled={searching}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {searching ? 'Looking up...' : 'Look up'}
          </button>
        </form>
      )}

      {!manual && cameraState === 'stopped' && searching && (
        <p className="text-slate-600">Barcode detected. Looking up product...</p>
      )}

      {!manual && cameraState === 'unavailable' && (
        <p className="text-slate-600">
          Camera barcode scanning is not available here.{' '}
          <button
            type="button"
            onClick={() => setManual(true)}
            className="underline"
          >
            Enter a barcode manually
          </button>
        </p>
      )}

      {error && (
        <p role="alert" className="mt-4 text-red-600">
          {error}
        </p>
      )}

      {lookup && (
        <div className="mt-6 space-y-4">
          {lookup.result.product && (
            <div className="rounded-lg border border-slate-300 p-4">
              <h2 className="font-semibold">Already in your catalog</h2>
              <p className="mt-1">{lookup.result.product.name}</p>
              <Link
                href={`/products/${lookup.result.product.id}`}
                className="mt-2 inline-block text-slate-600 underline"
              >
                View product
              </Link>
            </div>
          )}
          {draft && (
            <div className="rounded-lg border border-slate-300 p-4">
              <h2 className="font-semibold">
                Found on Open Food Facts
              </h2>
              <p className="mt-1">{draft.name}</p>
              {!draftIsComplete && (
                <p role="status" className="mt-2 text-amber-700">
                  Product data is incomplete. Review the package size and fill
                  in any missing main nutrients before saving.
                </p>
              )}
              {isStaff ? (
                <button
                  type="button"
                  onClick={() => createFromDraft(draft)}
                  className="mt-2 rounded-lg bg-slate-900 px-4 py-2 text-sm text-white"
                >
                  {draftIsComplete
                    ? 'Create product from this data'
                    : 'Review and complete product data'}
                </button>
              ) : (
                <p className="mt-2 text-slate-600">
                  A staff user must review and create this product.
                </p>
              )}
            </div>
          )}
          {!lookup.result.product && !lookup.result.openFoodFacts && (
            <div className="space-y-2">
              <p className="text-slate-600">
                No product found for barcode {lookup.barcode}.
              </p>
              {isStaff ? (
                <button
                  type="button"
                  onClick={() => createFromBarcode(lookup.barcode)}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white"
                >
                  Review and create product
                </button>
              ) : (
                <p className="text-slate-600">
                  A staff user must review and create this product.
                </p>
              )}
            </div>
          )}
          <button
            type="button"
            onClick={restart}
            className="text-slate-600 underline"
          >
            Scan another
          </button>
        </div>
      )}
    </div>
  )
}
