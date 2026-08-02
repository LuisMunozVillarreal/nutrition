import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('previous body fat prefills only an untouched measurement form', async () => {
  const { prefillPreviousBodyFat } = await import(
    '../src/app/measurements/new/measurementForm.ts'
  )

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
    prefillPreviousBodyFat({ bodyFatPerc: '', weight: '' }, null),
    { bodyFatPerc: '', weight: '' },
  )
})

test('new measurement page loads the latest body fat without loading weight', async () => {
  const source = await readFile(
    new URL('../src/app/measurements/new/page.tsx', import.meta.url),
    'utf8',
  )

  assert.match(source, /latestBodyFat/)
  assert.match(source, /prefillPreviousBodyFat/)
  assert.match(source, /useEffect/)
  assert.match(source, /catch\(/)
  assert.doesNotMatch(source, /latestWeight/)
})
