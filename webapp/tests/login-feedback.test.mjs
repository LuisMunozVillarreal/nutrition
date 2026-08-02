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
let callbackUrl = null
let navigationSuspender = null
let refreshCount = 0
let signInImplementation
let React

mock.module('next-auth/react', {
  namedExports: {
    signIn: (...args) => {
      authenticationCalls.push(args)
      return signInImplementation(...args)
    },
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
      }
    },
    useSearchParams: () =>
      new URLSearchParams(callbackUrl ? { callbackUrl } : undefined),
  },
})

React = await import('react')
const { act, cleanup, fireEvent, render, waitFor } = await import(
  '@testing-library/react'
)
const { default: LoginPage } = await import('../src/app/login/page.tsx')

function deferred() {
  let resolve
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function renderLogin() {
  const view = render(React.createElement(LoginPage))
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
  assert.equal(password.disabled, false)
  assert.equal(button.disabled, false)
  assert.equal(button.getAttribute('aria-busy'), 'false')
}

beforeEach(() => {
  authenticationCalls.length = 0
  pushedPaths.length = 0
  callbackUrl = null
  navigationSuspender = null
  refreshCount = 0
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
  assert.equal(controls.email.disabled, true)
  assert.equal(controls.password.disabled, true)
  assert.equal(controls.button.disabled, true)
  assert.equal(controls.button.getAttribute('aria-busy'), 'true')
  assert.ok(
    controls.button.querySelector('svg.animate-spin[aria-hidden="true"]'),
  )
  assert.equal(controls.view.getByRole('status').textContent, 'Signing in...')

  request.resolve({ ok: false })
  await waitFor(() => assertControlsEnabled(controls))
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

test('a rejected credentials request restores controls and shows retry guidance', async () => {
  signInImplementation = async () => {
    throw new Error('network unavailable')
  }
  const controls = renderLogin()

  fireEvent.submit(controls.form)

  const alert = await controls.view.findByRole('alert')
  assert.match(
    alert.textContent,
    /check your connection or credentials and try again/i,
  )
  assertControlsEnabled(controls)
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

test('feedback remains active during navigation and a mounted form releases its latch when navigation settles', async () => {
  const navigation = deferred()
  navigationSuspender = navigation
  signInImplementation = async () => ({ ok: true })
  const controls = renderLogin()

  fireEvent.submit(controls.form)

  await waitFor(() => assert.deepEqual(pushedPaths, ['/']))
  assert.equal(controls.email.disabled, true)
  assert.equal(controls.password.disabled, true)
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
