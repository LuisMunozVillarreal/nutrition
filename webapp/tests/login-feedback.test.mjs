import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const loginPageSource = await readFile(
  new URL('../src/app/login/page.tsx', import.meta.url),
  'utf8',
)

test('login submission shows accessible progress for the full credentials request', () => {
  assert.match(loginPageSource, /const submissionInFlight = useRef\(false\)/)
  assert.match(loginPageSource, /if \(submissionInFlight\.current\) return/)
  assert.match(loginPageSource, /submissionInFlight\.current = true[\s\S]*await signIn\('credentials'/)
  assert.match(loginPageSource, /const \[isSubmitting, setIsSubmitting\] = useState\(false\)/)
  assert.match(loginPageSource, /setIsSubmitting\(true\)[\s\S]*await signIn\('credentials'/)
  assert.match(loginPageSource, /disabled=\{isBusy\}/)
  assert.match(loginPageSource, /aria-busy=\{isBusy\}/)
  assert.match(loginPageSource, /animate-spin/)
  assert.match(loginPageSource, /aria-hidden="true"/)
  assert.match(loginPageSource, /<p role="status" aria-live="polite" className="sr-only">[\s\S]*?<\/p>[\s\S]*?<button/)
  assert.match(loginPageSource, /<LoaderCircle[^>]*aria-hidden="true"[^>]*\/>\s*Signing in\.\.\./)
})

test('failed login restores the button and renders retry guidance without an alert dialog', () => {
  assert.match(loginPageSource, /catch/)
  assert.match(loginPageSource, /submissionInFlight\.current = false/)
  assert.match(loginPageSource, /setIsSubmitting\(false\)/)
  assert.match(loginPageSource, /setError\(/)
  assert.match(loginPageSource, /role="alert"/)
  assert.match(loginPageSource, /check your connection or credentials and try again/i)
  assert.doesNotMatch(loginPageSource, /\balert\s*\(/)
})
