'use client'

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { graphqlRequest, gql } from '@/lib/graphql'
import {
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
  size: number
  sizeUnit: string
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

type CameraState = 'starting' | 'active' | 'unavailable'

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

export default function ScanPage() {
  const router = useRouter()
  const videoRef = useRef<HTMLVideoElement>(null)
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
    setSearching(true)
    setError(null)
    try {
      const res = await graphqlRequest<BarcodeLookupResult>(LOOKUP_QUERY, {
        barcode,
      })
      setLookup({ barcode, result: res.foodProductByBarcode })
    } catch (err) {
      setLookup(null)
      setError(
        err instanceof Error ? err.message : 'Barcode lookup failed',
      )
    } finally {
      setSearching(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    let activeStream: MediaStream | null = null
    // The video element is mounted whenever this effect runs: the initial
    // state renders it, and restart() re-renders it before bumping scanKey.
    const video = videoRef.current!

    const start = async () => {
      if (!isBarcodeDetectorSupported()) {
        setCameraState('unavailable')
        return
      }
      const detector = await createBarcodeDetector()
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
      const value = await readBarcodeFromVideo(video, detector)
      if (cancelled) return
      stopCameraStream(stream)
      activeStream = null
      if (!value) {
        setCameraState('unavailable')
        return
      }
      setCameraState('unavailable')
      searchBarcode(value)
    }

    void start()

    return () => {
      cancelled = true
      if (activeStream) stopCameraStream(activeStream)
    }
  }, [scanKey, searchBarcode])

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
      router.push(`/products/new?${params.toString()}`)
    },
    [router],
  )

  const restart = () => {
    setLookup(null)
    setError(null)
    setManual(false)
    setCameraState('starting')
    setScanKey((key) => key + 1)
  }

  const draft = lookup?.result.openFoodFacts

  return (
    <div className="max-w-2xl">
      <h1 className="page-title mb-6">Scan Barcode</h1>

      {!manual && cameraState !== 'unavailable' && (
        <div className="space-y-4">
          <video
            ref={videoRef}
            className="aspect-video w-full rounded-lg bg-slate-900"
            muted
            playsInline
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
              <button
                type="button"
                onClick={() => createFromDraft(draft)}
                className="mt-2 rounded-lg bg-slate-900 px-4 py-2 text-sm text-white"
              >
                Create product from this data
              </button>
            </div>
          )}
          {!lookup.result.product && !lookup.result.openFoodFacts && (
            <p className="text-slate-600">
              No product found for barcode {lookup.barcode}.
            </p>
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
