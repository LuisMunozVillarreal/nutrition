import { expect, test, vi } from 'vitest'
import { parseAuthorization, consentRedirect } from '../src/lib/healthAuthorization'

const origin = 'https://example.com'
const params = () => new URLSearchParams({
  issuer: origin,
  redirect_uri: 'com.nutrition.healthsync:/oauth2redirect',
  code_challenge: 'a'.repeat(43),
  code_challenge_method: 'S256',
  state: 's'.repeat(43),
  device_name: 'My phone',
})

test('consent preserves the exact issuer and sends only a code and state to Android', async () => {
  const request = parseAuthorization(params(), origin)
  const send = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ code: 'c'.repeat(43), state: request.state }) })
  const redirect = await consentRedirect(request, 'account-jwt', send)
  expect(send).toHaveBeenCalledWith('/api/health-sync/authorize/', expect.objectContaining({
    method: 'POST', credentials: 'omit', cache: 'no-store', redirect: 'error',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer account-jwt' },
  }))
  expect(redirect).toBe(`com.nutrition.healthsync:/oauth2redirect?code=${'c'.repeat(43)}&state=${'s'.repeat(43)}&issuer=https%3A%2F%2Fexample.com`)
})

test.each([
  ['issuer', 'https://other.example.com'],
  ['redirect_uri', 'https://evil.example.com/'],
  ['code_challenge_method', 'plain'],
  ['code_challenge', 'bad'], ['state', 'bad'], ['device_name', ''],
])('rejects invalid %s without starting consent', (key, value) => {
  const query = params(); query.set(key, value)
  expect(() => parseAuthorization(query, origin)).toThrow()
})

test('rejects duplicate parameters and HTTP origins', () => {
  const query = params(); query.append('state', 'x'.repeat(43))
  expect(() => parseAuthorization(query, origin)).toThrow()
  expect(() => parseAuthorization(params(), 'http://example.com')).toThrow()
})

test('handles missing account authentication, failed consent and mismatched responses', async () => {
  const request = parseAuthorization(params(), origin)
  await expect(consentRedirect(request, undefined, vi.fn())).rejects.toThrow()
  await expect(consentRedirect(request, 'jwt', vi.fn().mockResolvedValue({ ok: false }))).rejects.toThrow()
  for (const response of [{ code: 'bad', state: request.state }, { code: 'c'.repeat(43), state: 'bad' }]) {
    await expect(consentRedirect(request, 'jwt', vi.fn().mockResolvedValue({ ok: true, json: async () => response }))).rejects.toThrow()
  }
})
