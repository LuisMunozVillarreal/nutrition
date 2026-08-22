import {
  type GarminCallbackParseResult,
  parseGarminCallbackParams,
} from './garminCallback.ts'

export const GARMIN_CALLBACK_PATH = '/settings/garmin-callback'
export const GARMIN_CALLBACK_HANDOFF_MAX_AGE_MS = 5 * 60 * 1_000

const HANDOFF_STORAGE_KEY = 'nutrition.garmin.callback-handoff.v1'
const HANDOFF_VERSION = 1
const MAX_STORED_HANDOFF_LENGTH = 16_384
const SENSITIVE_CALLBACK_KEYS = [
  'code',
  'state',
  'error',
  'error_description',
] as const

interface SessionStorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

interface HistoryLike {
  readonly state: unknown
  replaceState(state: unknown, unused: string, url?: string | URL | null): void
}

interface SearchParamsLike {
  get(name: string): string | null
  getAll(name: string): string[]
}

type StoredCallbackResult = Exclude<GarminCallbackParseResult, { kind: 'invalid' }>

type StoredHandoff = {
  version: typeof HANDOFF_VERSION
  capturedAt: number
  result: StoredCallbackResult
}

const missingHandoff = (): GarminCallbackParseResult => ({
  kind: 'invalid',
  message:
    'Garmin callback details are missing or expired. Start the connection again.',
})

function clearHandoff(storage: SessionStorageLike): boolean {
  try {
    storage.removeItem(HANDOFF_STORAGE_KEY)
    return true
  } catch {
    return false
  }
}

function isStoredCallbackResult(value: unknown): value is StoredCallbackResult {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  if (candidate.kind === 'success') {
    return (
      typeof candidate.code === 'string' &&
      candidate.code.trim().length > 0 &&
      typeof candidate.state === 'string' &&
      candidate.state.trim().length > 0
    )
  }
  if (candidate.kind === 'providerError') {
    return (
      typeof candidate.error === 'string' &&
      candidate.error.trim().length > 0 &&
      typeof candidate.state === 'string' &&
      candidate.state.trim().length > 0
    )
  }
  return false
}

function isStoredHandoff(value: unknown): value is StoredHandoff {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Record<string, unknown>
  return (
    candidate.version === HANDOFF_VERSION &&
    Number.isSafeInteger(candidate.capturedAt) &&
    isStoredCallbackResult(candidate.result)
  )
}

export function captureGarminCallbackHandoff(
  pathname: string,
  params: SearchParamsLike,
  storage: SessionStorageLike,
  history: HistoryLike,
  now = Date.now(),
): boolean {
  if (
    !/^\/settings\/garmin-callback\/?$/.test(pathname) ||
    !SENSITIVE_CALLBACK_KEYS.some((key) => params.getAll(key).length > 0)
  ) {
    return false
  }

  const result = parseGarminCallbackParams(params)

  try {
    history.replaceState(history.state, '', GARMIN_CALLBACK_PATH)
  } catch {
    clearHandoff(storage)
    return false
  }

  clearHandoff(storage)
  if (result.kind === 'invalid' || !Number.isSafeInteger(now)) return true

  const handoff: StoredHandoff = {
    version: HANDOFF_VERSION,
    capturedAt: now,
    result,
  }
  try {
    storage.setItem(HANDOFF_STORAGE_KEY, JSON.stringify(handoff))
  } catch {
    clearHandoff(storage)
  }
  return true
}

export function consumeGarminCallbackHandoff(
  storage: SessionStorageLike,
  now = Date.now(),
): GarminCallbackParseResult {
  let serialized: string | null
  try {
    serialized = storage.getItem(HANDOFF_STORAGE_KEY)
    if (!clearHandoff(storage)) return missingHandoff()
  } catch {
    return missingHandoff()
  }

  if (!serialized || serialized.length > MAX_STORED_HANDOFF_LENGTH) {
    return missingHandoff()
  }

  try {
    const handoff: unknown = JSON.parse(serialized)
    if (!isStoredHandoff(handoff)) return missingHandoff()
    const age = now - handoff.capturedAt
    if (
      !Number.isSafeInteger(now) ||
      age < 0 ||
      age > GARMIN_CALLBACK_HANDOFF_MAX_AGE_MS
    ) {
      return missingHandoff()
    }
    return handoff.result
  } catch {
    return missingHandoff()
  }
}
