export type GarminCallbackProviderError = {
  kind: 'providerError'
  error: string
  errorDescription: string | null
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
  const providerError = valueOrNull(getSingleValue(params, 'error'))
  const providerErrorDescription = valueOrNull(
    getSingleValue(params, 'error_description'),
  )
  if (providerError) {
    return {
      kind: 'providerError',
      error: providerError,
      errorDescription: providerErrorDescription
        ? providerErrorDescription
        : null,
    }
  }

  const code = valueOrNull(getSingleValue(params, 'code'))
  const state = valueOrNull(getSingleValue(params, 'state'))

  if (!code || !state) {
    return {
      kind: 'invalid',
      message:
        'Expected exactly one Garmin OAuth code and state parameter on callback.',
    }
  }

  return { kind: 'success', code, state }
}
