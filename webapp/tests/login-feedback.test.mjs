import assert from 'node:assert/strict'
import { after, afterEach, beforeEach, mock, test } from 'node:test'
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  pretendToBeVisual: true,
  url: 'https://example.com/login',
})

for (const property of [
  'window',
  'document',
  'navigator',
  'HTMLElement',
  'HTMLInputElement',
  'HTMLButtonElement',
  'Node',
  'Event',
  'MouseEvent',
  'MutationObserver',
]) {
  Object.defineProperty(globalThis, property, {
    configurable: true,
    value: dom.window[property],
  })
}
globalThis.getComputedStyle = dom.window.getComputedStyle.bind(dom.window)
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const authenticationCalls = []
const pushedPaths = []
const replacedPaths = []
let callbackUrl = null
let navigationSuspender = null
let refreshCount = 0
let sessionData = null
let sessionStatus = 'unauthenticated'
let signInImplementation
let React

mock.module('next-auth/react', {
  namedExports: {
    signIn: (...args) => {
      authenticationCalls.push(args)
      return signInImplementation(...args)
    },
    useSession: () => ({ data: sessionData, status: sessionStatus }),
  },
})

mock.module('next/navigation', {
  namedExports: {
    useRouter: () => {
      const [navigationAttempt, setNavigationAttempt] = React.useState(0)
      if (navigationAttempt > 0 && navigationSuspender) {
        throw navigationSuspender.promise
      }

      return {
        push: (path) => {
          pushedPaths.push(path)
          if (navigationSuspender) {
            setNavigationAttempt((attempt) => attempt + 1)
          }
        },
        refresh: () => {
          refreshCount += 1
        },
        replace: (path) => {
          replacedPaths.push(path)
        },
      }
    },
    usePathname: () => '/login',
    useSearchParams: () =>
      new URLSearchParams(callbackUrl ? { callbackUrl } : undefined),
  },
})

React = await import('react')
const { act, cleanup, fireEvent, render, waitFor } = await import(
  '@testing-library/react'
)
const { default: LoginPage } = await import('../src/app/login/page.tsx')
const { default: AppShell } = await import('../src/components/AppShell.tsx')

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, reject, resolve }
}

function renderLogin({ withShell = false } = {}) {
  const login = React.createElement(LoginPage)
  const element = withShell
    ? React.createElement(AppShell, null, login)
    : login
  const view = render(element)
  const email = view.getByPlaceholderText('Email')
  const password = view.getByPlaceholderText('Password')
  const button = view.getByRole('button', { name: 'Sign In' })
  const form = button.closest('form')
  assert.ok(form)

  fireEvent.change(email, { target: { value: 'person@example.com' } })
  fireEvent.change(password, { target: { value: 'correct horse' } })

  return { button, email, form, password, view }
}

function assertControlsEnabled({ button, email, password }) {
  assert.equal(email.disabled, false)
  assert.equal(email.readOnly, false)
  assert.equal(password.disabled, false)
  assert.equal(password.readOnly, false)
  assert.equal(button.disabled, false)
  assert.equal(button.getAttribute('aria-busy'), 'false')
}

beforeEach(() => {
  authenticationCalls.length = 0
  pushedPaths.length = 0
  replacedPaths.length = 0
  callbackUrl = null
  navigationSuspender = null
  refreshCount = 0
  sessionData = null
  sessionStatus = 'unauthenticated'
  signInImplementation = async () => ({ ok: false })
})

afterEach(() => cleanup())
after(() => dom.window.close())

test('a deferred credentials request blocks duplicate submissions and shows progress', async () => {
  const request = deferred()
  signInImplementation = () => request.promise
  const controls = renderLogin()

  fireEvent.submit(controls.form)
  fireEvent.submit(controls.form)

  assert.equal(authenticationCalls.length, 1)
  assert.equal(controls.email.disabled, false)
  assert.equal(controls.email.readOnly, true)
  assert.equal(controls.password.disabled, false)
  assert.equal(controls.password.readOnly, true)
  assert.equal(controls.button.disabled, true)
  assert.equal(controls.button.getAttribute('aria-busy'), 'true')
  assert.ok(
    controls.button.querySelector('svg.animate-spin[aria-hidden="true"]'),
  )
  assert.equal(controls.view.getByRole('status').textContent, 'Signing in...')

  request.resolve({ ok: false })
  await waitFor(() => assertControlsEnabled(controls))
})

test('the progress spinner stops for reduced motion while live text remains available', async () => {
  const request = deferred()
  signInImplementation = () => request.promise
  const controls = renderLogin()

  fireEvent.submit(controls.form)

  const spinner = controls.button.querySelector('svg[aria-hidden="true"]')
  assert.ok(spinner)
  assert.equal(spinner.classList.contains('animate-spin'), true)
  assert.equal(spinner.classList.contains('motion-reduce:animate-none'), true)
  assert.equal(controls.view.getByRole('status').textContent, 'Signing in...')

  request.resolve({ ok: false })
  await waitFor(() => assertControlsEnabled(controls))
})

test('an unresolved credentials request offers safe page recovery while keeping duplicate submissions blocked', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  callbackUrl = '/products?sort=name'
  signInImplementation = () => new Promise(() => {})
  const controls = renderLogin()

  fireEvent.submit(controls.form)
  assert.equal(
    controls.view.queryByRole('link', { name: /reload login page/i }),
    null,
  )

  await act(async () => t.mock.timers.tick(10_000))

  const recoveryLink = controls.view.getByRole('link', {
    name: /reload login page/i,
  })
  assert.equal(
    recoveryLink.getAttribute('href'),
    '/login?callbackUrl=%2Fproducts%3Fsort%3Dname',
  )
  assert.match(
    controls.view.getByRole('status').textContent,
    /taking longer than expected/i,
  )
  fireEvent.submit(controls.form)
  assert.equal(authenticationCalls.length, 1)
  assert.equal(controls.email.readOnly, true)
  assert.equal(controls.password.readOnly, true)
  assert.equal(controls.button.disabled, true)
  assert.equal(controls.button.getAttribute('aria-busy'), 'true')
})

test('a resolved unsuccessful credentials result restores controls and shows retry guidance', async () => {
  signInImplementation = async () => ({ ok: false })
  const controls = renderLogin()

  fireEvent.submit(controls.form)

  const alert = await controls.view.findByRole('alert')
  assert.match(
    alert.textContent,
    /check your connection or credentials and try again/i,
  )
  assertControlsEnabled(controls)
})

test('keyboard submission preserves text-entry focus while busy and focuses the retry button after an unsuccessful result', async () => {
  const request = deferred()
  signInImplementation = () => request.promise
  const controls = renderLogin()
  controls.password.focus()

  fireEvent.submit(controls.form)

  assert.equal(controls.password.disabled, false)
  assert.equal(controls.password.readOnly, true)
  assert.equal(document.activeElement, controls.password)

  await act(async () => {
    request.resolve({ ok: false })
    await request.promise
  })

  await controls.view.findByRole('alert')
  await waitFor(() => assert.equal(document.activeElement, controls.button))
  assert.equal(controls.password.readOnly, false)
})

test('button submission restores focus to the retry button after a rejected request', async () => {
  const request = deferred()
  signInImplementation = () => request.promise
  const controls = renderLogin()
  controls.button.focus()

  fireEvent.click(controls.button)
  assert.equal(controls.button.disabled, true)
  controls.button.blur()

  await act(async () => {
    request.reject(new Error('network unavailable'))
    await request.promise.catch(() => {})
  })

  const alert = await controls.view.findByRole('alert')
  assert.match(
    alert.textContent,
    /check your connection or credentials and try again/i,
  )
  assertControlsEnabled(controls)
  assert.equal(document.activeElement, controls.button)
})

test('successful authentication refreshes and navigates to the safe callback path', async () => {
  callbackUrl = '/products?sort=name'
  signInImplementation = async () => ({ ok: true })
  const controls = renderLogin()

  fireEvent.submit(controls.form)

  await waitFor(() => assert.deepEqual(pushedPaths, ['/products?sort=name']))
  assert.equal(refreshCount, 1)
  assert.equal(authenticationCalls[0][0], 'credentials')
  assert.equal(
    authenticationCalls[0][1].callbackUrl,
    '/products?sort=name',
  )
})

test('the authenticated session shell preserves the login callback instead of racing it to the landing page', async () => {
  callbackUrl = '/products?sort=name'
  signInImplementation = async () => {
    sessionData = { user: { isStaff: false } }
    sessionStatus = 'authenticated'
    return { ok: true }
  }
  const controls = renderLogin({ withShell: true })

  fireEvent.submit(controls.form)
  await waitFor(() => assert.deepEqual(pushedPaths, ['/products?sort=name']))

  controls.view.rerender(
    React.createElement(AppShell, null, React.createElement(LoginPage)),
  )
  await waitFor(() =>
    assert.deepEqual(replacedPaths, ['/products?sort=name']),
  )
})

test('a never-settling post-authentication navigation retains callback recovery and duplicate blocking', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  callbackUrl = '/products?sort=name'
  navigationSuspender = deferred()
  signInImplementation = async () => ({ ok: true })
  const controls = renderLogin()

  await act(async () => {
    fireEvent.submit(controls.form)
    await Promise.resolve()
  })
  assert.deepEqual(pushedPaths, ['/products?sort=name'])

  await act(async () => t.mock.timers.tick(10_000))

  const recoveryLink = controls.view.getByRole('link', {
    name: /reload login page/i,
  })
  assert.equal(recoveryLink.getAttribute('href'), '/products?sort=name')
  fireEvent.submit(controls.form)
  assert.equal(authenticationCalls.length, 1)
})

test('feedback remains active during navigation and a mounted form releases its latch when navigation settles', async () => {
  const navigation = deferred()
  navigationSuspender = navigation
  signInImplementation = async () => ({ ok: true })
  const controls = renderLogin()

  fireEvent.submit(controls.form)

  await waitFor(() => assert.deepEqual(pushedPaths, ['/']))
  assert.equal(controls.email.disabled, false)
  assert.equal(controls.email.readOnly, true)
  assert.equal(controls.password.disabled, false)
  assert.equal(controls.password.readOnly, true)
  assert.equal(controls.button.disabled, true)
  assert.ok(
    controls.button.querySelector('svg.animate-spin[aria-hidden="true"]'),
  )
  assert.equal(controls.view.getByRole('status').textContent, 'Signing in...')
  fireEvent.submit(controls.form)
  assert.equal(authenticationCalls.length, 1)

  await act(async () => {
    navigationSuspender = null
    navigation.resolve()
    await navigation.promise
  })
  await waitFor(() => assertControlsEnabled(controls))
  fireEvent.submit(controls.form)
  await waitFor(() => assert.equal(authenticationCalls.length, 2))
})
