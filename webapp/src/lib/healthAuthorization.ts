const redirects = new Set([
  'com.nutrition.healthsync:/oauth2redirect',
  'com.nutrition.healthsync.testing:/oauth2redirect',
])
const opaque = /^[A-Za-z0-9_-]{43}$/

export interface AuthorizationRequest {
  issuer: string
  redirect_uri: string
  code_challenge: string
  code_challenge_method: string
  state: string
  device_name: string
}

export function parseAuthorization(query: URLSearchParams, origin: string): AuthorizationRequest {
  const keys = ['issuer', 'redirect_uri', 'code_challenge', 'code_challenge_method', 'state', 'device_name'] as const
  if (keys.some(key => query.getAll(key).length !== 1)) throw new Error('Invalid sign-in request')
  const request = Object.fromEntries(keys.map(key => [key, query.get(key)])) as unknown as AuthorizationRequest
  if (
    !origin.startsWith('https://') || request.issuer !== origin ||
    !redirects.has(request.redirect_uri) || request.code_challenge_method !== 'S256' ||
    !opaque.test(request.code_challenge) || !opaque.test(request.state) ||
    !request.device_name.trim() || request.device_name.length > 120
  ) throw new Error('Invalid sign-in request')
  return request
}

export async function consentRedirect(
  request: AuthorizationRequest, token: string | undefined, send: typeof fetch = fetch,
): Promise<string> {
  if (!token) throw new Error('Sign in again to connect this device')
  const response = await send('/api/health-sync/authorize/', {
    method: 'POST', credentials: 'omit', cache: 'no-store', redirect: 'error',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(request),
  })
  if (!response.ok) throw new Error('Could not authorize this device. Try signing in again.')
  const result = await response.json()
  if (!opaque.test(result.code) || result.state !== request.state) throw new Error('Invalid authorization response')
  return `${request.redirect_uri}?${new URLSearchParams({ code: result.code, state: request.state, issuer: request.issuer })}`
}
