import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { buildSchema, parse, validate } from 'graphql'

const servingSchema = buildSchema(`
  type Query {
    foodProduct(id: ID!): FoodProduct
  }

  type FoodProduct {
    servings: [Serving!]!
  }

  type Serving {
    id: ID!
    servingSize: Float!
    servingUnit: String!
    energyKcal: Float!
    proteinG: Float!
    fatG: Float!
    carbsG: Float!
  }
`)

async function readGraphqlOperation(pagePath, constantName) {
  const source = await readFile(new URL(pagePath, import.meta.url), 'utf8')
  const match = source.match(
    new RegExp(`const ${constantName} = gql` + '`([\\s\\S]*?)`'),
  )
  assert.ok(match, `${constantName} GraphQL operation was not found`)
  return match[1]
}

test('custom intake macros are converted from per-serving values to totals', async () => {
  const { buildCustomIntakeVariables } = await import(
    '../src/app/intakes/new/intakeVariables.ts'
  )
  const variables = buildCustomIntakeVariables({
    dayId: '7',
    meal: 'lunch',
    numServings: '2.5',
    energyKcal: '120',
    proteinG: '10',
    fatG: '4',
    carbsG: '',
  })

  assert.deepEqual(variables, {
    dayId: 7,
    meal: 'lunch',
    numServings: 2.5,
    energyKcal: 300,
    proteinG: 25,
    fatG: 10,
    carbsG: 0,
  })
})

test('custom intake edit converts totals to per-serving values and recalculates totals', async () => {
  const { buildCustomIntakeEditForm, buildCustomIntakeUpdateVariables } = await import(
    '../src/app/intakes/[id]/intakeVariables.ts'
  )
  const form = buildCustomIntakeEditForm({
    meal: 'dinner',
    numServings: 2,
    energyKcal: 300,
    proteinG: 25,
    fatG: 10,
    carbsG: 40,
  })

  assert.deepEqual(form, {
    meal: 'dinner',
    numServings: '2',
    energyKcal: '150',
    proteinG: '12.5',
    fatG: '5',
    carbsG: '20',
  })

  form.numServings = '3'
  assert.deepEqual(buildCustomIntakeUpdateVariables('9', form), {
    id: '9',
    meal: 'dinner',
    numServings: 3,
    energyKcal: 450,
    proteinG: 37.5,
    fatG: 15,
    carbsG: 60,
  })

  const editPage = await readFile(
    new URL('../src/app/intakes/[id]/page.tsx', import.meta.url),
    'utf8',
  )
  assert.match(editPage, /buildCustomIntakeEditForm\(res\.intake\)/)
  assert.match(editPage, /buildCustomIntakeUpdateVariables\(id, form\)/)
})

test('cupboard purchase dates remain stable across timezones and pages', async () => {
  const {
    formatPurchaseDate,
    localDateInputValue,
    purchaseDateToISOString,
  } = await import('../src/app/cupboard/purchaseDate.ts')

  assert.equal(
    localDateInputValue(new Date('2025-01-01T01:00:00.000Z'), 480),
    '2024-12-31',
  )
  assert.equal(
    purchaseDateToISOString('2025-01-15'),
    '2025-01-15T00:00:00.000Z',
  )
  assert.equal(
    formatPurchaseDate('2025-01-15T00:00:00.000Z', 'short'),
    'Jan 15, 2025',
  )

  const newPage = await readFile(
    new URL('../src/app/cupboard/new/page.tsx', import.meta.url),
    'utf8',
  )
  assert.match(newPage, /localDateInputValue\(\)/)
  assert.match(newPage, /purchaseDateToISOString\(form\.purchasedAt\)/)

  for (const pagePath of [
    '../src/app/cupboard/page.tsx',
    '../src/app/cupboard/[id]/page.tsx',
  ]) {
    const page = await readFile(new URL(pagePath, import.meta.url), 'utf8')
    assert.match(page, /formatPurchaseDate\(/)
  }
})

test('serving edit query has no unused GraphQL variables', async () => {
  const operation = await readGraphqlOperation(
    '../src/app/servings/[id]/page.tsx',
    'SERVING_QUERY',
  )

  const errors = validate(servingSchema, parse(operation))

  assert.deepEqual(errors.map((error) => error.message), [])
})

test('positive quantity forms declare native minimum constraints', async () => {
  const constrainedFields = [
    ['../src/app/intakes/new/page.tsx', 'numServings'],
    ['../src/app/intakes/[id]/page.tsx', 'numServings'],
    ['../src/app/servings/new/page.tsx', 'servingSize'],
    ['../src/app/servings/[id]/page.tsx', 'servingSize'],
    ['../src/app/products/new/page.tsx', 'size'],
    ['../src/app/products/[id]/page.tsx', 'size'],
    ['../src/app/recipes/new/page.tsx', 'size'],
    ['../src/app/recipes/[id]/page.tsx', 'size'],
  ]

  for (const [pagePath, fieldName] of constrainedFields) {
    const page = await readFile(new URL(pagePath, import.meta.url), 'utf8')
    const field = page.match(
      new RegExp(`<FormField[^>]*name=["']${fieldName}["'][^>]*/>`),
    )
    assert.ok(field, `${fieldName} field was not found in ${pagePath}`)
    assert.match(field[0], /min=["']0\.1["']/)
  }
})

test('measurement forms constrain weight and body fat to valid ranges', async () => {
  const formFieldTag = (page, fieldName, pagePath) => {
    const marker = `name="${fieldName}"`
    const markerIndex = page.indexOf(marker)
    assert.ok(markerIndex >= 0, `${fieldName} field was not found in ${pagePath}`)
    const startIndex = page.lastIndexOf('<FormField', markerIndex)
    const endIndex = page.indexOf('/>', markerIndex)
    assert.ok(startIndex >= 0 && endIndex >= 0, `${fieldName} tag is incomplete`)
    return page.slice(startIndex, endIndex + 2)
  }

  for (const pagePath of [
    '../src/app/measurements/new/page.tsx',
    '../src/app/measurements/[id]/page.tsx',
  ]) {
    const page = await readFile(new URL(pagePath, import.meta.url), 'utf8')
    const weight = formFieldTag(page, 'weight', pagePath)
    const bodyFat = formFieldTag(page, 'bodyFatPerc', pagePath)
    assert.match(weight, /min="0\.1"/)
    assert.match(bodyFat, /min="0\.1"/)
    assert.match(bodyFat, /max="99\.9"/)
  }
})

test('custom intake macro fields declare native non-negative constraints', async () => {
  for (const pagePath of [
    '../src/app/intakes/new/page.tsx',
    '../src/app/intakes/[id]/page.tsx',
  ]) {
    const page = await readFile(new URL(pagePath, import.meta.url), 'utf8')
    for (const fieldName of ['energyKcal', 'proteinG', 'fatG', 'carbsG']) {
      const field = page.match(
        new RegExp(`<FormField[^>]*name=["']${fieldName}["'][^>]*/>`),
      )
      assert.ok(field, `${fieldName} field was not found in ${pagePath}`)
      assert.match(field[0], /min=["']0["']/)
    }
  }
})

test('week plan forms constrain nutrition parameters to server ranges', async () => {
  for (const pagePath of [
    '../src/app/plans/new/page.tsx',
    '../src/app/plans/[id]/page.tsx',
  ]) {
    const page = await readFile(new URL(pagePath, import.meta.url), 'utf8')
    for (const [fieldName, minimum, maximum] of [
      ['proteinGKg', '0.1', null],
      ['fatPerc', '0.1', '99.9'],
      ['deficit', '0', null],
    ]) {
      const field = page.match(
        new RegExp(`<FormField[^>]*name=["']${fieldName}["'][^>]*/>`),
      )
      assert.ok(field, `${fieldName} field was not found in ${pagePath}`)
      assert.match(field[0], new RegExp(`min=["']${minimum.replace('.', '\\.')}["']`))
      if (maximum) {
        assert.match(field[0], new RegExp(`max=["']${maximum.replace('.', '\\.')}["']`))
      }
    }
  }
})

test('product and recipe nutrient fields declare non-negative constraints', async () => {
  for (const pagePath of [
    '../src/app/products/new/page.tsx',
    '../src/app/products/[id]/page.tsx',
    '../src/app/recipes/new/page.tsx',
    '../src/app/recipes/[id]/page.tsx',
  ]) {
    const page = await readFile(new URL(pagePath, import.meta.url), 'utf8')
    for (const fieldName of [
      'energyKcal',
      'proteinG',
      'fatG',
      'carbsG',
      'saturatedFatG',
      'sugarsG',
      'fibreG',
      'saltG',
    ]) {
      const field = page.match(
        new RegExp(`<FormField[^>]*name=["']${fieldName}["'][^>]*/>`),
      )
      assert.ok(field, `${fieldName} field was not found in ${pagePath}`)
      assert.match(field[0], /min=["']0["']/)
    }
  }
})

test('EntityForm uses native form submission so invalid fields block saves', async () => {
  const entityForm = await readFile(
    new URL('../src/components/EntityForm.tsx', import.meta.url),
    'utf8',
  )
  const buttonTag = (testId) => {
    const marker = `data-testid="${testId}"`
    const markerIndex = entityForm.indexOf(marker)
    assert.ok(markerIndex >= 0, `${testId} button was not found`)
    const startIndex = entityForm.lastIndexOf('<button', markerIndex)
    const endIndex = entityForm.indexOf('>', markerIndex)
    assert.ok(startIndex >= 0 && endIndex >= 0, `${testId} opening tag was not found`)
    return entityForm.slice(startIndex, endIndex + 1)
  }

  assert.match(entityForm, /<form\b[^>]*onSubmit=\{handleSubmit\}[^>]*>/)
  assert.match(entityForm, /const handleSubmit[\s\S]*?event\.preventDefault\(\)/)
  assert.match(buttonTag('save-btn'), /type="submit"/)
  assert.doesNotMatch(buttonTag('save-btn'), /onClick=/)
  assert.match(buttonTag('back-btn'), /type="button"/)
  assert.match(buttonTag('delete-btn'), /type="button"/)
})

test('all product, recipe, and serving forms use the canonical fluid-ounce value', async () => {
  const formPaths = [
    '../src/app/products/new/page.tsx',
    '../src/app/products/[id]/page.tsx',
    '../src/app/recipes/new/page.tsx',
    '../src/app/recipes/[id]/page.tsx',
    '../src/app/servings/new/page.tsx',
    '../src/app/servings/[id]/page.tsx',
  ]

  for (const path of formPaths) {
    const source = await readFile(new URL(path, import.meta.url), 'utf8')
    assert.match(
      source,
      /\{\s*value:\s*'floz',\s*label:\s*'fl oz'\s*\}/,
      `${path} does not submit the canonical fluid-ounce value`,
    )
    assert.doesNotMatch(
      source,
      /value:\s*'fl oz'/,
      `${path} still submits the display label as the fluid-ounce value`,
    )
  }
})

test('Cypress waits for hydrated forms before replacing controlled values', async () => {
  const readSource = async (path) => {
    try {
      return await readFile(new URL(path, import.meta.url), 'utf8')
    } catch {
      return ''
    }
  }

  const entityForm = await readSource('../src/components/EntityForm.tsx')
  assert.match(entityForm, /const \[hydrated, setHydrated\] = useState\(false\)/)
  assert.match(entityForm, /useEffect\(\(\) => setHydrated\(true\), \[\]\)/)
  assert.match(entityForm, /data-testid="form-hydrating"/)
  assert.match(entityForm, /data-testid="form-ready"/)

  const appShell = await readSource('../src/components/AppShell.tsx')
  assert.match(appShell, /const \{ data: session, status \} = useSession\(\)/)
  assert.match(appShell, /if \(status === 'loading'\)/)
  assert.match(appShell, /data-testid="session-loading"/)
  assert.ok(
    appShell.indexOf("status === 'loading'") < appShell.indexOf('if (!session)'),
    'AppShell renders children before the session is settled',
  )

  const formSupport = await readSource('../cypress/support/form.ts')
  assert.match(formSupport, /export function waitForFormReady/)
  assert.match(formSupport, /data-testid="form-ready"/)
  assert.match(formSupport, /export function replaceInputValue/)

  for (const path of [
    '../cypress/support/step_definitions/cupboard.ts',
    '../cypress/support/step_definitions/exercises.ts',
    '../cypress/support/step_definitions/measurements.ts',
  ]) {
    const source = await readSource(path)
    const readyIndex = source.indexOf('waitForFormReady()')
    const inputIndex = source.indexOf('replaceInputValue(')
    assert.ok(readyIndex >= 0, `${path} does not wait for hydration`)
    assert.ok(inputIndex > readyIndex, `${path} edits inputs before hydration`)
  }
})
