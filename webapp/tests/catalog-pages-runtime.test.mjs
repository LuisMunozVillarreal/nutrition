import assert from 'node:assert/strict'
import { afterEach, test, vi } from 'vitest'
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost/' })
for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Node', 'Event', 'MouseEvent']) {
  Object.defineProperty(globalThis, key, { configurable: true, value: dom.window[key] })
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true

let session = null
let routeId = 'item-1'
let foodId = null
let searchParams = new URLSearchParams()
let graphqlImpl = async () => ({})
let graphqlCalls = []
let entityProps
let tableProps = []
let fieldProps = new Map()
let readonlyProps = []
let mountedRoot
let mountedContainer

vi.doMock('next-auth/react', () => ({ useSession: () => ({ data: session }) }))
vi.doMock('next/navigation', () => ({
  useParams: () => ({ id: routeId }),
  useSearchParams: () => ({
    get: (name) => (name === 'foodId' ? foodId : searchParams.get(name)),
    toString: () => searchParams.toString(),
  }),
}))
vi.doMock('next/link', () => ({
  default: ({ href, children, ...props }) =>
    React.createElement('a', { href, ...props }, children),
}))
vi.doMock('@/lib/graphql', () => ({
  gql: (parts, ...values) => String.raw({ raw: parts }, ...values),
  graphqlRequest: async (...args) => {
    graphqlCalls.push(args)
    return graphqlImpl(...args)
  },
}))
vi.doMock('@/components/EntityForm', () => ({
  default: (props) => {
    entityProps = props
    return React.createElement(
      'section',
      { 'data-testid': 'entity-form' },
      React.createElement('h1', null, props.title),
      props.fieldsets.map((fieldset, index) =>
        React.createElement('div', { key: index }, fieldset.title, fieldset.content),
      ),
    )
  },
}))

const Field = (props) => {
  fieldProps.set(props.name, props)
  return React.createElement('div', { 'data-field': props.name }, String(props.value ?? ''))
}
const Readonly = (props) => {
  readonlyProps.push(props)
  return React.createElement('div', { 'data-readonly': props.label }, String(props.value ?? ''))
}
vi.doMock('@/components/FormField', () => ({
  FormField: Field,
  SelectField: Field,
  TextareaField: Field,
  CheckboxField: Field,
  ReadonlyField: Readonly,
}))
vi.doMock('@/components/DataTable', () => ({
  default: (props) => {
    tableProps.push(props)
    return React.createElement(
      'div',
      { 'data-testid': 'table' },
      props.loading
        ? 'loading'
        : props.data.map((row) =>
            React.createElement(
              'div',
              { key: row.id },
              props.columns.map((column) =>
                React.createElement('span', { key: column.key }, String(column.accessor(row))),
              ),
            ),
          ),
    )
  },
}))

async function mount(Component) {
  mountedContainer = document.createElement('div')
  document.body.appendChild(mountedContainer)
  mountedRoot = createRoot(mountedContainer)
  await act(async () => { mountedRoot.render(React.createElement(Component)) })
  return mountedContainer
}

async function settle(check) {
  let lastError
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await act(async () => { await new Promise((resolve) => setImmediate(resolve)) })
    try {
      check()
      return
    } catch (error) {
      lastError = error
    }
  }
  throw lastError
}

async function change(name, value) {
  const props = fieldProps.get(name)
  assert.ok(props, `field ${name} is rendered`)
  await act(async () => { props.onChange(name, value) })
}

async function save() {
  await act(async () => { await entityProps.onSave() })
}

async function remove() {
  await act(async () => { await entityProps.onDelete() })
}

function latestTable() {
  return tableProps.at(-1)
}

function queryContains(text) {
  return graphqlCalls.some(([query]) => query.includes(text))
}

afterEach(async () => {
  if (mountedRoot) await act(async () => { mountedRoot.unmount() })
  mountedContainer?.remove()
  mountedRoot = undefined
  mountedContainer = undefined
  session = null
  routeId = 'item-1'
  foodId = null
  searchParams = new URLSearchParams()
  graphqlImpl = async () => ({})
  graphqlCalls = []
  entityProps = undefined
  tableProps = []
  fieldProps = new Map()
  readonlyProps = []
  vi.restoreAllMocks()
})

test('products list loads and formats rows, with navigation only for staff', async () => {
  graphqlImpl = async () => ({
    foodProducts: [
      { id: 'p1', name: 'Oats', brand: null, size: 500, sizeUnit: 'g' },
      { id: 'p2', name: 'Milk', brand: 'Farm', size: 1, sizeUnit: 'l' },
    ],
  })
  const { default: Page } = await import('../src/app/products/page.tsx')
  const container = await mount(Page)
  await settle(() => assert.equal(latestTable().loading, false))
  assert.match(container.textContent, /—Oats500 g/)
  assert.match(container.textContent, /FarmMilk1 l/)
  assert.equal(container.querySelector('[data-testid="scan-link"]'), null)
  assert.equal(latestTable().rowHref, undefined)
  assert.equal(latestTable().addHref, undefined)

  session = {}
  await act(async () => { mountedRoot.render(React.createElement(Page)) })
  assert.equal(latestTable().rowHref, undefined)
  session = { user: { isStaff: false } }
  await act(async () => { mountedRoot.render(React.createElement(Page)) })
  assert.equal(latestTable().addHref, undefined)
  session = { user: { isStaff: true } }
  await act(async () => { mountedRoot.render(React.createElement(Page)) })
  assert.equal(latestTable().rowHref({ id: 'p9' }), '/products/p9')
  assert.equal(latestTable().addHref, '/products/new')
})

test('products list logs request failures', async () => {
  const failure = new Error('offline')
  graphqlImpl = async () => { throw failure }
  const errors = []
  vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args))
  const { default: Page } = await import('../src/app/products/page.tsx')
  await mount(Page)
  await settle(() => assert.equal(latestTable().loading, false))
  assert.deepEqual(errors, [['Failed to fetch food products', failure]])
  assert.deepEqual(latestTable().data, [])
})

test('recipes list loads and rounds every macro, with navigation only for staff', async () => {
  graphqlImpl = async () => ({ recipes: [{
    id: 'r1', name: 'Stew', numServings: 2.5,
    energyKcal: 10.4, proteinG: 2.5, fatG: 3.6, carbsG: 4.49,
  }] })
  const { default: Page } = await import('../src/app/recipes/page.tsx')
  const container = await mount(Page)
  await settle(() => assert.equal(latestTable().loading, false))
  assert.match(container.textContent, /Stew2.510344/)
  assert.equal(latestTable().rowHref, undefined)
  session = {}
  await act(async () => { mountedRoot.render(React.createElement(Page)) })
  session = { user: { isStaff: false } }
  await act(async () => { mountedRoot.render(React.createElement(Page)) })
  session = { user: { isStaff: true } }
  await act(async () => { mountedRoot.render(React.createElement(Page)) })
  assert.equal(latestTable().rowHref({ id: 'r8' }), '/recipes/r8')
  assert.equal(latestTable().addHref, '/recipes/new')
})

test('recipes list logs request failures', async () => {
  const failure = new Error('recipes unavailable')
  graphqlImpl = async () => { throw failure }
  const errors = []
  vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args))
  const { default: Page } = await import('../src/app/recipes/page.tsx')
  await mount(Page)
  await settle(() => assert.equal(latestTable().loading, false))
  assert.deepEqual(errors, [['Failed to fetch recipes', failure]])
})

test('cupboard list formats active and finished inventory and handles failures', async () => {
  graphqlImpl = async () => ({ cupboardItems: [
    { id: 'c1', foodLabel: 'Oats', purchasedAt: '2025-01-15T00:00:00Z', consumedPerc: 12.6, remainingServings: 3.25, finished: false },
    { id: 'c2', foodLabel: 'Milk', purchasedAt: '2025-01-16T00:00:00Z', consumedPerc: 100, remainingServings: 0, finished: true },
  ] })
  const { default: Page } = await import('../src/app/cupboard/page.tsx')
  const container = await mount(Page)
  await settle(() => assert.equal(latestTable().loading, false))
  assert.match(container.textContent, /OatsJan 15, 202513%3.3 servings/)
  assert.match(container.textContent, /MilkJan 16, 2025Finished0.0 servings/)
  assert.equal(latestTable().rowHref({ id: 'c9' }), '/cupboard/c9')
  assert.equal(latestTable().addHref, '/cupboard/new')

  await act(async () => { mountedRoot.unmount() })
  mountedRoot = undefined
  tableProps = []
  graphqlCalls = []
  const failure = new Error('cupboard unavailable')
  graphqlImpl = async () => { throw failure }
  const errors = []
  vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args))
  await mount(Page)
  await settle(() => assert.equal(latestTable().loading, false))
  assert.deepEqual(errors, [['Failed to fetch cupboard items', failure]])
})

test('new product synchronizes incompatible units and submits nullable and numeric values', async () => {
  const { default: Page } = await import('../src/app/products/new/page.tsx')
  await mount(Page)
  assert.equal(entityProps.title, 'New Food Product')
  assert.equal(fieldProps.get('nutritionalInfoUnit').value, 'g')
  assert.equal(fieldProps.get('energyKcal').value, '')
  await assert.rejects(
    save(),
    /Enter all required main nutrients before saving/,
  )
  assert.equal(graphqlCalls.length, 0)

  await change('name', 'Granola')
  await change('sizeUnit', 'ml')
  assert.equal(fieldProps.get('nutritionalInfoUnit').value, 'ml')
  await change('sizeUnit', 'oz')
  await change('brand', 'Maker')
  await change('barcode', '123')
  await change('notes', 'Crunchy')
  await change('nutritionalInfoSize', '2.5')
  await change('size', '7.5')
  await change('numServings', '3')
  await change('energyKcal', '101.5')
  await change('proteinG', '4.5')
  await change('fatG', '5.5')
  await change('carbsG', '6.5')
  for (const [name, value] of [['saturatedFatG', '1.1'], ['sugarsG', '2.2'], ['fibreG', '3.3'], ['saltG', '4.4']]) await change(name, value)
  await save()
  assert.deepEqual(graphqlCalls.at(-1)[1], {
    name: 'Granola', brand: 'Maker', barcode: '123', notes: 'Crunchy',
    nutritionalInfoSize: 2.5, nutritionalInfoUnit: 'oz', size: 7.5, sizeUnit: 'oz', numServings: 3,
    energyKcal: 101.5, proteinG: 4.5, fatG: 5.5, carbsG: 6.5,
    saturatedFatG: 1.1, sugarsG: 2.2, fibreG: 3.3, saltG: 4.4,
  })
  assert.equal(entityProps.saving, false)

  await change('brand', '')
  await change('barcode', '')
  for (const name of ['saturatedFatG', 'sugarsG', 'fibreG', 'saltG']) await change(name, '')
  await save()
  const blankVariables = graphqlCalls.at(-1)[1]
  assert.equal(blankVariables.brand, null)
  assert.equal(blankVariables.barcode, null)
  for (const name of ['saturatedFatG', 'sugarsG', 'fibreG', 'saltG']) assert.equal(blankVariables[name], null)
})

test('new product prefills the form from scan query parameters', async () => {
  searchParams = new URLSearchParams([
    ['fromBarcodeScan', '1'],
    ['barcode', '3017620422003'],
    ['brand', 'Ferrero'],
    ['name', 'Nutella'],
    ['size', '350'],
    ['sizeUnit', 'g'],
    ['numServings', '1'],
    ['nutritionalInfoSize', '100'],
    ['nutritionalInfoUnit', 'g'],
    ['energyKcal', '539'],
    ['proteinG', '6.3'],
    ['fatG', '30.9'],
    ['carbsG', '57.5'],
    ['saturatedFatG', '10.6'],
    ['sugarsG', '56.3'],
    ['saltG', '0.11'],
  ])
  const { default: Page } = await import('../src/app/products/new/page.tsx')
  await mount(Page)
  assert.equal(entityProps.title, 'New Food Product')
  assert.equal(fieldProps.get('barcode').value, '3017620422003')
  assert.equal(fieldProps.get('name').value, 'Nutella')
  assert.equal(fieldProps.get('brand').value, 'Ferrero')
  assert.equal(fieldProps.get('size').value, '350')
  assert.equal(fieldProps.get('sizeUnit').value, 'g')
  assert.equal(fieldProps.get('nutritionalInfoSize').value, '100')
  assert.equal(fieldProps.get('energyKcal').value, '539')
  assert.equal(fieldProps.get('saltG').value, '0.11')
  assert.equal(fieldProps.get('fibreG').value, '')
  assert.equal(fieldProps.get('notes').value, '')
  await save()
  assert.deepEqual(graphqlCalls.at(-1)[1], {
    name: 'Nutella', brand: 'Ferrero', barcode: '3017620422003', notes: '',
    nutritionalInfoSize: 100, nutritionalInfoUnit: 'g', size: 350, sizeUnit: 'g', numServings: 1,
    energyKcal: 539, proteinG: 6.3, fatG: 30.9, carbsG: 57.5,
    saturatedFatG: 10.6, sugarsG: 56.3, fibreG: null, saltG: 0.11,
  })
})

test('new product returns scanned intake context after creation', async () => {
  searchParams = new URLSearchParams([
    ['fromBarcodeScan', '1'],
    ['intakeDayId', 'day 7'],
    ['returnTo', 'https://attacker.example/'],
    ['barcode', '3017620422003'],
    ['name', 'Oats'],
    ['size', '500'],
    ['sizeUnit', 'g'],
    ['numServings', '5'],
    ['nutritionalInfoSize', '100'],
    ['nutritionalInfoUnit', 'g'],
    ['energyKcal', '100'],
    ['proteinG', '10'],
    ['fatG', '2'],
    ['carbsG', '12'],
  ])
  graphqlImpl = async () => ({ createFoodProduct: { id: 'product/1' } })
  const { default: Page } = await import('../src/app/products/new/page.tsx')
  await mount(Page)
  let destination
  await act(async () => {
    destination = await entityProps.onSave()
  })
  assert.equal(
    destination,
    '/intakes/new?dayId=day+7&productId=product%2F1',
  )
  assert.doesNotMatch(destination, /returnTo|attacker/)
})

test('new product continues a scanner meal flow without a preselected day', async () => {
  searchParams = new URLSearchParams([
    ['fromBarcodeScan', '1'], ['fromMealLog', '1'],
    ['barcode', '3017620422003'], ['name', 'Oats'],
    ['size', '500'], ['sizeUnit', 'g'], ['numServings', '5'],
    ['nutritionalInfoSize', '100'], ['nutritionalInfoUnit', 'g'],
    ['energyKcal', '100'], ['proteinG', '10'], ['fatG', '2'], ['carbsG', '12'],
  ])
  graphqlImpl = async () => ({ createFoodProduct: { id: 'product/1' } })
  const { default: Page } = await import('../src/app/products/new/page.tsx')
  await mount(Page)

  let destination
  await act(async () => { destination = await entityProps.onSave() })

  assert.equal(destination, '/intakes/new?productId=product%2F1')
})

test('new product remounts when its trusted scan context changes', async () => {
  const required = [
    ['fromBarcodeScan', '1'], ['barcode', '111'], ['name', 'First'],
    ['size', '100'], ['sizeUnit', 'g'], ['numServings', '1'],
    ['nutritionalInfoSize', '100'], ['nutritionalInfoUnit', 'g'],
    ['energyKcal', '1'], ['proteinG', '2'], ['fatG', '3'], ['carbsG', '4'],
    ['intakeDayId', '7'],
  ]
  searchParams = new URLSearchParams(required)
  const { default: Page } = await import('../src/app/products/new/page.tsx')
  await mount(Page)
  assert.equal(fieldProps.get('name').value, 'First')

  searchParams = new URLSearchParams(required.map(([name, value]) => {
    if (name === 'name') return [name, 'Second']
    if (name === 'barcode') return [name, '222']
    if (name === 'intakeDayId') return [name, '8']
    return [name, value]
  }))
  await act(async () => { mountedRoot.render(React.createElement(Page)) })
  assert.equal(fieldProps.get('name').value, 'Second')
  graphqlImpl = async () => ({ createFoodProduct: { id: 'p2' } })
  let destination
  await act(async () => { destination = await entityProps.onSave() })
  assert.equal(destination, '/intakes/new?dayId=8&productId=p2')
  assert.equal(graphqlCalls.at(-1)[1].name, 'Second')
  assert.equal(graphqlCalls.at(-1)[1].barcode, '222')
})

test('new product requires a valid package size for incomplete scan data', async () => {
  searchParams = new URLSearchParams([
    ['fromBarcodeScan', '1'],
    ['barcode', '3017620422003'],
  ])
  const { default: Page } = await import('../src/app/products/new/page.tsx')
  await mount(Page)
  assert.equal(fieldProps.get('size').value, '')
  await assert.rejects(save(), /Enter a valid package size before saving/)
  await change('size', 'Infinity')
  await assert.rejects(save(), /Enter a valid package size before saving/)
  await change('size', '0')
  await assert.rejects(save(), /Enter a valid package size before saving/)
  assert.equal(graphqlCalls.length, 0)
})

test('new recipe updates all fields and submits both populated and empty optional values', async () => {
  const { default: Page } = await import('../src/app/recipes/new/page.tsx')
  await mount(Page)
  await change('name', 'Pie')
  await change('brand', 'Bakery')
  await change('description', 'Warm')
  await change('size', '8.5')
  await change('sizeUnit', 'container')
  await change('numServings', '4')
  await change('energyKcal', '201')
  await change('proteinG', '2')
  await change('fatG', '3')
  await change('carbsG', '30')
  for (const [name, value] of [['saturatedFatG', '1'], ['sugarsG', '2'], ['fibreG', '3'], ['saltG', '4']]) await change(name, value)
  await save()
  assert.deepEqual(graphqlCalls.at(-1)[1], {
    name: 'Pie', brand: 'Bakery', description: 'Warm', size: 8.5, sizeUnit: 'container', numServings: 4,
    energyKcal: 201, proteinG: 2, fatG: 3, carbsG: 30,
    saturatedFatG: 1, sugarsG: 2, fibreG: 3, saltG: 4,
  })
  await change('brand', '')
  for (const name of ['saturatedFatG', 'sugarsG', 'fibreG', 'saltG']) await change(name, '')
  await save()
  assert.equal(graphqlCalls.at(-1)[1].brand, null)
  for (const name of ['saturatedFatG', 'sugarsG', 'fibreG', 'saltG']) assert.equal(graphqlCalls.at(-1)[1][name], null)
})

test('product edit hydrates, formats servings, changes units, updates, and deletes', async () => {
  routeId = 'p7'
  const product = {
    id: 'p7', name: 'Yogurt', brand: 'Dairy', barcode: '999', notes: 'Plain',
    nutritionalInfoSize: 100, nutritionalInfoUnit: 'g', size: 500, sizeUnit: 'g', numServings: 5,
    energyKcal: 60, proteinG: 4, fatG: 3, carbsG: 5,
    saturatedFatG: 2, sugarsG: 4, fibreG: 0, saltG: null,
    servings: [{ id: 's1', servingSize: 125, servingUnit: 'g', energyKcal: 75.4, proteinG: 5.6 }],
  }
  graphqlImpl = async (query) => query.includes('query GetFoodProduct') ? { foodProduct: product } : {}
  const { default: Page } = await import('../src/app/products/[id]/page.tsx')
  const container = await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Food Product'))
  assert.equal(fieldProps.get('brand').value, 'Dairy')
  assert.match(container.textContent, /125 g756/)
  assert.equal(latestTable().rowHref({ id: 's9' }), '/servings/s9?foodId=p7')
  assert.equal(latestTable().addHref, '/servings/new?foodId=p7')

  await change('name', 'Greek Yogurt')
  await change('sizeUnit', 'ml')
  assert.equal(fieldProps.get('nutritionalInfoUnit').value, 'ml')
  await change('sizeUnit', 'oz')
  await save()
  const update = graphqlCalls.at(-1)[1]
  assert.equal(update.id, 'p7')
  assert.equal(update.name, 'Greek Yogurt')
  assert.equal(update.brand, 'Dairy')
  assert.equal(update.saltG, null)
  await remove()
  assert.deepEqual(graphqlCalls.at(-1)[1], { id: 'p7' })
})

test('product edit covers empty fallbacks, missing records, and request errors', async () => {
  const { default: Page } = await import('../src/app/products/[id]/page.tsx')
  graphqlImpl = async (query) => query.includes('query GetFoodProduct') ? { foodProduct: {
    name: 'Bare', brand: null, barcode: null, notes: '', nutritionalInfoSize: 1, nutritionalInfoUnit: 'g',
    size: 1, sizeUnit: 'g', numServings: 1, energyKcal: 1, proteinG: 1, fatG: 1, carbsG: 1,
    saturatedFatG: null, sugarsG: null, fibreG: null, saltG: null, servings: undefined,
  } } : {}
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Food Product'))
  assert.equal(fieldProps.get('brand').value, '')
  assert.deepEqual(latestTable().data, [])
  await save()
  assert.equal(graphqlCalls.at(-1)[1].brand, null)
  assert.equal(graphqlCalls.at(-1)[1].barcode, null)

  await act(async () => { mountedRoot.unmount() })
  mountedRoot = undefined
  entityProps = undefined
  graphqlImpl = async () => ({ foodProduct: null })
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Food Product'))

  await act(async () => { mountedRoot.unmount() })
  mountedRoot = undefined
  entityProps = undefined
  const failure = new Error('product failed')
  graphqlImpl = async () => { throw failure }
  const errors = []
  vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args))
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Food Product'))
  assert.deepEqual(errors, [['Failed to fetch food product', failure]])
})

test('recipe edit covers editable aggregates, ingredient columns, update, and delete', async () => {
  routeId = 'r7'
  const recipe = {
    id: 'r7', name: 'Soup', brand: 'Kitchen', description: 'Hot', nutrientsFromIngredients: false,
    size: 400, sizeUnit: 'g', numServings: 2, energyKcal: 120, proteinG: 10, fatG: 4, carbsG: 15,
    saturatedFatG: 1, sugarsG: 2, fibreG: 3, saltG: 4,
    ingredients: [{ id: 'i1', foodLabel: 'Carrot', numServings: 1.5, energyKcal: 10.4, proteinG: 2.5, fatG: 0.6, carbsG: 3.5 }],
  }
  graphqlImpl = async (query) => query.includes('query GetRecipe') ? { recipe } : {}
  const { default: Page } = await import('../src/app/recipes/[id]/page.tsx')
  const container = await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Recipe'))
  assert.match(container.textContent, /Carrot1.510314/)
  assert.equal(fieldProps.get('energyKcal').value, '120')
  await change('name', 'New Soup')
  await save()
  assert.equal(graphqlCalls.at(-1)[1].name, 'New Soup')
  assert.equal(graphqlCalls.at(-1)[1].brand, 'Kitchen')
  await remove()
  assert.deepEqual(graphqlCalls.at(-1)[1], { id: 'r7' })
})

test('recipe edit renders ingredient-derived values and covers empty and missing fallbacks', async () => {
  const { default: Page } = await import('../src/app/recipes/[id]/page.tsx')
  graphqlImpl = async (query) => query.includes('query GetRecipe') ? { recipe: {
    name: 'Derived', brand: null, description: null, nutrientsFromIngredients: true,
    size: 2, sizeUnit: 'serving', numServings: 2, energyKcal: 20, proteinG: 3, fatG: 4, carbsG: 5,
    saturatedFatG: null, sugarsG: null, fibreG: null, saltG: null, ingredients: undefined,
  } } : {}
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Recipe'))
  assert.equal(fieldProps.get('brand').value, '')
  assert.ok(readonlyProps.some((props) => props.label === 'Size' && props.value === '2'))
  assert.ok(readonlyProps.some((props) => props.label === 'Energy (kcal)' && props.value === '20'))
  assert.deepEqual(latestTable().data, [])
  await save()
  assert.equal(graphqlCalls.at(-1)[1].brand, null)

  await act(async () => { mountedRoot.unmount() })
  mountedRoot = undefined
  entityProps = undefined
  graphqlImpl = async () => ({ recipe: null })
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Recipe'))
})

test('recipe edit logs request failures', async () => {
  const failure = new Error('recipe failed')
  graphqlImpl = async () => { throw failure }
  const errors = []
  vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args))
  const { default: Page } = await import('../src/app/recipes/[id]/page.tsx')
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Recipe'))
  assert.deepEqual(errors, [['Failed to fetch recipe', failure]])
})

test('new serving handles absent food context without requesting or saving', async () => {
  const { default: Page } = await import('../src/app/servings/new/page.tsx')
  await mount(Page)
  assert.equal(entityProps.backHref, '/products')
  assert.equal(graphqlCalls.length, 0)
  await save()
  assert.equal(graphqlCalls.length, 0)
})

test('new serving loads units, changes fields, saves, and tolerates a missing product', async () => {
  foodId = 'p1'
  graphqlImpl = async (query) => query.includes('query GetServingProductUnits')
    ? { foodProduct: { sizeUnit: 'g', nutritionalInfoUnit: 'g' } }
    : {}
  const { default: Page } = await import('../src/app/servings/new/page.tsx')
  await mount(Page)
  await settle(() => assert.ok(queryContains('query GetServingProductUnits')))
  assert.equal(entityProps.backHref, '/products/p1')
  await change('servingSize', '2.5')
  await change('servingUnit', 'oz')
  await save()
  assert.deepEqual(graphqlCalls.at(-1)[1], { foodId: 'p1', servingSize: 2.5, servingUnit: 'oz' })

  await act(async () => { mountedRoot.unmount() })
  mountedRoot = undefined
  graphqlCalls = []
  graphqlImpl = async () => ({ foodProduct: null })
  await mount(Page)
  await settle(() => assert.equal(graphqlCalls.length, 1))
})

test('new serving logs unit lookup failures', async () => {
  foodId = 'p2'
  const failure = new Error('units failed')
  graphqlImpl = async () => { throw failure }
  const errors = []
  vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args))
  const { default: Page } = await import('../src/app/servings/new/page.tsx')
  await mount(Page)
  await settle(() => assert.equal(errors.length, 1))
  assert.deepEqual(errors, [['Failed to fetch product units', failure]])
})

test('serving edit handles absent food context and uses product fallback link', async () => {
  const { default: Page } = await import('../src/app/servings/[id]/page.tsx')
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Serving'))
  assert.equal(entityProps.backHref, '/products')
  assert.equal(graphqlCalls.length, 0)
})

test('serving edit finds the route serving, displays macros, updates, and deletes', async () => {
  routeId = 's2'
  foodId = 'p3'
  graphqlImpl = async (query) => query.includes('query GetServing') ? { foodProduct: {
    sizeUnit: 'g', nutritionalInfoUnit: 'g', servings: [
      { id: 's1', servingSize: 1, servingUnit: 'g', energyKcal: 1, proteinG: 1, fatG: 1, carbsG: 1 },
      { id: 's2', servingSize: 25, servingUnit: 'g', energyKcal: 50.4, proteinG: 6.5, fatG: 2.4, carbsG: 8.5 },
    ],
  } } : {}
  const { default: Page } = await import('../src/app/servings/[id]/page.tsx')
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Serving'))
  assert.equal(entityProps.backHref, '/products/p3')
  assert.equal(fieldProps.get('servingSize').value, '25')
  assert.ok(readonlyProps.some((props) => props.label === 'Energy (kcal)' && props.value === 50))
  await change('servingSize', '30.5')
  await change('servingUnit', 'oz')
  await save()
  assert.deepEqual(graphqlCalls.at(-1)[1], { id: 's2', servingSize: 30.5, servingUnit: 'oz' })
  await remove()
  assert.deepEqual(graphqlCalls.at(-1)[1], { id: 's2' })
})

test('serving edit covers products without servings and completely missing products', async () => {
  foodId = 'p4'
  const { default: Page } = await import('../src/app/servings/[id]/page.tsx')
  graphqlImpl = async () => ({ foodProduct: { sizeUnit: 'ml', nutritionalInfoUnit: 'ml', servings: undefined } })
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Serving'))
  assert.equal(fieldProps.get('servingSize').value, '')

  await act(async () => { mountedRoot.unmount() })
  mountedRoot = undefined
  entityProps = undefined
  graphqlImpl = async () => ({ foodProduct: null })
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Serving'))
})

test('serving edit logs request failures', async () => {
  foodId = 'p5'
  const failure = new Error('serving failed')
  graphqlImpl = async () => { throw failure }
  const errors = []
  vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args))
  const { default: Page } = await import('../src/app/servings/[id]/page.tsx')
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Serving'))
  assert.deepEqual(errors, [['Failed to fetch serving', failure]])
})

test('new cupboard item sorts branded and unbranded foods, selects the first, changes, and saves', async () => {
  graphqlImpl = async (query) => query.includes('query') ? {
    foodProducts: [
      { id: 'p1', name: 'Oats', brand: null },
      { id: 'p2', name: 'Milk', brand: 'Farm' },
    ],
    recipes: [
      { id: 'r1', name: 'Soup', brand: null },
      { id: 'r2', name: 'Pie', brand: 'Bake' },
    ],
  } : {}
  const { default: Page } = await import('../src/app/cupboard/new/page.tsx')
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Add to Cupboard'))
  const options = fieldProps.get('foodId').options
  assert.deepEqual(options.map((option) => option.label), [
    'Product: Farm Milk', 'Product: Oats', 'Recipe: Bake Pie', 'Recipe: Soup',
  ])
  assert.equal(fieldProps.get('foodId').value, 'p2')
  await change('foodId', 'r1')
  await change('purchasedAt', '2025-02-03')
  await change('consumedPerc', '12.5')
  await save()
  assert.deepEqual(graphqlCalls.at(-1)[1], {
    foodId: 'r1', purchasedAt: '2025-02-03T00:00:00.000Z', consumedPerc: 12.5,
  })
})

test('new cupboard item handles empty choices and lookup failures', async () => {
  const { default: Page } = await import('../src/app/cupboard/new/page.tsx')
  graphqlImpl = async () => ({ foodProducts: [], recipes: [] })
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Add to Cupboard'))
  assert.equal(fieldProps.get('foodId').value, '')

  await act(async () => { mountedRoot.unmount() })
  mountedRoot = undefined
  entityProps = undefined
  const failure = new Error('foods failed')
  graphqlImpl = async () => { throw failure }
  const errors = []
  vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args))
  await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Add to Cupboard'))
  assert.deepEqual(errors, [['Failed to fetch foods', failure]])
})

test('cupboard edit hydrates item, changes progress, formats date, updates, and deletes', async () => {
  routeId = 'c7'
  graphqlImpl = async (query) => query.includes('query GetCupboardItem') ? { cupboardItem: {
    id: 'c7', foodId: 'p1', foodLabel: 'Oats', purchasedAt: '2025-01-15T00:00:00Z', consumedPerc: 25,
  } } : {}
  const { default: Page } = await import('../src/app/cupboard/[id]/page.tsx')
  const container = await mount(Page)
  await settle(() => assert.equal(entityProps?.title, 'Edit Oats'))
  assert.match(container.textContent, /Purchased on: January 15, 2025/)
  await change('consumedPerc', '66.5')
  assert.equal(container.querySelector('[style]').style.width, '66.5%')
  await save()
  assert.deepEqual(graphqlCalls.at(-1)[1], { id: 'c7', consumedPerc: 66.5 })
  await remove()
  assert.deepEqual(graphqlCalls.at(-1)[1], { id: 'c7' })
})

test('cupboard edit renders not-found state and logs request failures', async () => {
  const { default: Page } = await import('../src/app/cupboard/[id]/page.tsx')
  graphqlImpl = async () => ({ cupboardItem: null })
  let container = await mount(Page)
  await settle(() => assert.match(container.textContent, /Item not found/))

  await act(async () => { mountedRoot.unmount() })
  mountedRoot = undefined
  const failure = new Error('item failed')
  graphqlImpl = async () => { throw failure }
  const errors = []
  vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args))
  container = await mount(Page)
  await settle(() => assert.match(container.textContent, /Item not found/))
  assert.deepEqual(errors, [['Failed to fetch item', failure]])
})
