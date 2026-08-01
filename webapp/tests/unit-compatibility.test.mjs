import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'vitest'

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
  assert.equal(isCompatibleUnitPair('unknown', 'g'), false)
  assert.equal(isCompatibleUnitPair('ml', 'g'), false)
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
  assert.deepEqual(servingUnitChoices('g', 'ml'), [])
})

test('manual recipe choices fail loudly if the canonical unit catalog is corrupted', async () => {
  const { recipeUnitChoices, UNIT_CHOICES } = await import('../src/lib/units.ts')
  const index = UNIT_CHOICES.findIndex(({ value }) => value === 'g')
  const [removed] = UNIT_CHOICES.splice(index, 1)

  try {
    assert.throws(() => recipeUnitChoices(false, 'g'), /Unknown recipe unit: g/)
  } finally {
    UNIT_CHOICES.splice(index, 0, removed)
  }
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

test('recipe unit choices reject contextual aggregate units but allow concrete conversion', async () => {
  const { recipeUnitChoices } = await import('../src/lib/units.ts')

  assert.deepEqual(
    recipeUnitChoices(false, 'g').map(({ value }) => value),
    ['g', 'ml', 'floz', 'oz', 'container', 'serving'],
  )
  assert.deepEqual(
    recipeUnitChoices(true, 'g').map(({ value }) => value),
    ['mg', 'g', 'kg', 'oz', 'lb'],
  )
  assert.deepEqual(
    recipeUnitChoices(true, 'ml').map(({ value }) => value),
    ['ml', 'cl', 'l', 'c', 'floz', 'tbsp', 'tsp', 'pt'],
  )
})

test('recipe edit honors ingredient-derived aggregate authority', async () => {
  const source = await readFile(
    new URL('../src/app/recipes/[id]/page.tsx', import.meta.url),
    'utf8',
  )

  assert.match(source, /nutrientsFromIngredients/)
  assert.match(source, /recipeUnitChoices\(nutrientsFromIngredients, form\.sizeUnit\)/)
  assert.match(source, /Ingredient-derived aggregates \(read-only\)/)

  for (const fieldName of [
    'size',
    'energyKcal',
    'proteinG',
    'fatG',
    'carbsG',
    'saturatedFatG',
    'sugarsG',
    'fibreG',
    'saltG',
  ]) {
    assert.match(
      source,
      new RegExp(`nutrientsFromIngredients[\\s\\S]*?<ReadonlyField[^>]*label=[^>]*value=\\{form\\.${fieldName}\\}`),
      `${fieldName} is not rendered read-only for ingredient-derived recipes`,
    )
  }
})
