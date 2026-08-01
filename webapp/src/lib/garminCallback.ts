export type GarminCallbackProviderError = {
  kind: 'providerError'
  error: string
  state: string
}

export type GarminCallbackSuccess = {
  kind: 'success'
  code: string
  state: string
}

export type GarminCallbackInvalidError = {
  kind: 'invalid'
  message: string
}

export type GarminCallbackParseResult =
  | GarminCallbackSuccess
  | GarminCallbackProviderError
  | GarminCallbackInvalidError

const invalidCallback = (): GarminCallbackInvalidError => ({
  kind: 'invalid',
  message:
    'Expected exactly one Garmin OAuth code and state parameter on callback.',
})

export function garminProviderErrorMessage(error: string): string {
  if (error === 'access_denied') return 'Garmin sign-in was cancelled.'
  return 'Garmin sign-in failed. Please try again.'
}

function getSingleValue(
  params: SearchParamsLike,
  key: string,
): string | null {
  const values = params.getAll(key)
  if (values.length !== 1) return null
  return values[0] ?? null
}

function valueOrNull(value: string | null): string | null {
  if (value === null) return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

type SearchParamsLike = {
  get: (name: string) => string | null
  getAll: (name: string) => string[]
}

export function parseGarminCallbackParams(
  params: SearchParamsLike,
): GarminCallbackParseResult {
  const providerErrorValues = params.getAll('error')
  if (providerErrorValues.length > 0) {
    const providerError = valueOrNull(getSingleValue(params, 'error'))
    const state = valueOrNull(getSingleValue(params, 'state'))
    if (
      !providerError ||
      !state ||
      params.getAll('code').length > 0 ||
      params.getAll('error_description').length > 1
    ) {
      return invalidCallback()
    }
    return {
      kind: 'providerError',
      error: providerError,
      state,
    }
  }

  const code = valueOrNull(getSingleValue(params, 'code'))
  const state = valueOrNull(getSingleValue(params, 'state'))

  if (!code || !state || params.getAll('error_description').length > 0) {
    return invalidCallback()
  }

  return { kind: 'success', code, state }
}
