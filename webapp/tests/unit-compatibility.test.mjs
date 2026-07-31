import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  compatibleUnits,
  isCompatibleUnitPair,
  servingUnitChoices,
} from '../src/lib/units.ts'

test('unit compatibility mirrors backend mass volume and contextual rules', () => {
  assert.equal(isCompatibleUnitPair('g', 'kg'), true)
  assert.equal(isCompatibleUnitPair('ml', 'floz'), true)
  assert.equal(isCompatibleUnitPair('unit', 'unit'), true)
  assert.equal(isCompatibleUnitPair('container', 'container'), true)
  assert.equal(isCompatibleUnitPair('g', 'ml'), false)
  assert.equal(isCompatibleUnitPair('unit', 'serving'), false)
})

test('product compatibility choices keep only the selected dimension', () => {
  assert.deepEqual(
    compatibleUnits('g').map(({ value }) => value),
    ['mg', 'g', 'kg', 'oz', 'lb'],
  )
  assert.deepEqual(
    compatibleUnits('unit').map(({ value }) => value),
    ['unit'],
  )
})

test('serving choices retain container semantics but reject other dimensions', () => {
  assert.deepEqual(
    servingUnitChoices('g', 'g').map(({ value }) => value),
    ['mg', 'g', 'kg', 'oz', 'lb', 'container', 'serving'],
  )
  assert.deepEqual(
    servingUnitChoices('unit', 'unit').map(({ value }) => value),
    ['unit', 'container', 'serving'],
  )
})

test('product and serving forms apply compatibility choices', async () => {
  const sources = await Promise.all(
    [
      '../src/app/products/new/page.tsx',
      '../src/app/products/[id]/page.tsx',
      '../src/app/servings/new/page.tsx',
      '../src/app/servings/[id]/page.tsx',
    ].map((path) => readFile(new URL(path, import.meta.url), 'utf8')),
  )

  for (const source of sources.slice(0, 2)) {
    assert.match(source, /compatibleUnits\(form\.sizeUnit\)/)
    assert.match(source, /isCompatibleUnitPair/)
  }
  for (const source of sources.slice(2)) {
    assert.match(source, /servingUnitChoices/)
    assert.match(source, /sizeUnit/)
    assert.match(source, /nutritionalInfoUnit/)
  }
})
