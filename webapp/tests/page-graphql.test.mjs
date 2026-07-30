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
