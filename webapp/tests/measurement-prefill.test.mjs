import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'vitest'

test('previous body fat prefills only an untouched measurement form', async () => {
  const {
    loadAndPrefillPreviousBodyFat,
    prefillPreviousBodyFat,
  } = await import('../src/app/measurements/new/measurementForm.ts')

  assert.deepEqual(
    prefillPreviousBodyFat({ bodyFatPerc: '', weight: '' }, 18.4),
    { bodyFatPerc: '18.4', weight: '' },
  )
  assert.deepEqual(
    prefillPreviousBodyFat({ bodyFatPerc: '19.2', weight: '' }, 18.4),
    { bodyFatPerc: '19.2', weight: '' },
  )
  assert.deepEqual(
    prefillPreviousBodyFat({ bodyFatPerc: '', weight: '' }, 18.4, true),
    { bodyFatPerc: '', weight: '' },
  )
  assert.deepEqual(
    prefillPreviousBodyFat({ bodyFatPerc: '', weight: '80' }, null),
    { bodyFatPerc: '', weight: '80' },
  )

  let form = { bodyFatPerc: '', weight: '' }
  let touched = false
  let cancelled = false
  let resolveLookup
  const lookupResult = new Promise((resolve) => {
    resolveLookup = resolve
  })
  const loading = loadAndPrefillPreviousBodyFat({
    lookup: () => lookupResult,
    updateForm: (update) => {
      form = update(form)
    },
    isTouched: () => touched,
    isCancelled: () => cancelled,
    onError: (error) => assert.fail(error),
  })

  touched = true
  form = { bodyFatPerc: '', weight: '' }
  resolveLookup(18.4)
  await loading

  assert.deepEqual(form, { bodyFatPerc: '', weight: '' })

  touched = false
  await loadAndPrefillPreviousBodyFat({
    lookup: async () => 18.4,
    updateForm: (update) => {
      form = update(form)
    },
    isTouched: () => touched,
    isCancelled: () => cancelled,
    onError: (error) => assert.fail(error),
  })
  assert.deepEqual(form, { bodyFatPerc: '18.4', weight: '' })

  form = { bodyFatPerc: '', weight: '' }
  cancelled = true
  await loadAndPrefillPreviousBodyFat({
    lookup: async () => 20,
    updateForm: (update) => {
      form = update(form)
    },
    isTouched: () => false,
    isCancelled: () => cancelled,
    onError: (error) => assert.fail(error),
  })
  assert.deepEqual(form, { bodyFatPerc: '', weight: '' })

  let capturedError
  await loadAndPrefillPreviousBodyFat({
    lookup: async () => {
      throw new Error('lookup failed')
    },
    updateForm: (update) => {
      form = update(form)
    },
    isTouched: () => false,
    isCancelled: () => false,
    onError: (error) => {
      capturedError = error
    },
  })
  assert.equal(capturedError?.message, 'lookup failed')
  assert.deepEqual(form, { bodyFatPerc: '', weight: '' })

  // A lookup that fails after cancellation must not surface the error.
  let cancelledErrorCalls = 0
  await loadAndPrefillPreviousBodyFat({
    lookup: async () => {
      throw new Error('late lookup failure')
    },
    updateForm: (update) => {
      form = update(form)
    },
    isTouched: () => false,
    isCancelled: () => true,
    onError: () => {
      cancelledErrorCalls += 1
    },
  })
  assert.equal(cancelledErrorCalls, 0)
  assert.deepEqual(form, { bodyFatPerc: '', weight: '' })
})

test('new measurement page loads the latest body fat without loading weight', async () => {
  const source = await readFile(
    new URL('../src/app/measurements/new/page.tsx', import.meta.url),
    'utf8',
  )

  assert.match(source, /latestMeasurement/)
  assert.match(source, /bodyFatPerc/)
  assert.match(source, /loadAndPrefillPreviousBodyFat/)
  assert.match(source, /useEffect/)
  assert.match(source, /onError:/)
  assert.doesNotMatch(source, /dashboard\(/)
  assert.doesNotMatch(source, /latestWeight/)
})
