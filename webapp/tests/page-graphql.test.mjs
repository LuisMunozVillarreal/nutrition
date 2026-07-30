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

test('serving edit query has no unused GraphQL variables', async () => {
  const operation = await readGraphqlOperation(
    '../src/app/servings/[id]/page.tsx',
    'SERVING_QUERY',
  )

  const errors = validate(servingSchema, parse(operation))

  assert.deepEqual(errors.map((error) => error.message), [])
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
