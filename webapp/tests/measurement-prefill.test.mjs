import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'vitest'

test('new measurement page leaves optional body fat blank', async () => {
  const source = await readFile(
    new URL('../src/app/measurements/new/page.tsx', import.meta.url),
    'utf8',
  )

  assert.match(source, /bodyFatPerc: optionalNumberVariable\(form\.bodyFatPerc\)/)
  assert.doesNotMatch(source, /PREVIOUS_BODY_FAT_QUERY/)
  assert.doesNotMatch(source, /latestMeasurement/)
  assert.doesNotMatch(source, /loadAndPrefillPreviousBodyFat/)
  const bodyFatField = source.slice(
    source.indexOf('label="Body Fat (%)"'),
    source.indexOf('/>', source.indexOf('label="Body Fat (%)"')),
  )
  assert.doesNotMatch(bodyFatField, /required/)
})
