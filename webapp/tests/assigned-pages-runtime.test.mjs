import assert from 'node:assert/strict'
import { afterEach, test, vi } from 'vitest'
import React from 'react'
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://example.com/' })
for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Event', 'MouseEvent']) {
  Object.defineProperty(globalThis, key, { configurable: true, value: dom.window[key] })
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true
globalThis.confirm = () => true
const rtlModule = await import('@testing-library/react')
const { act, cleanup, fireEvent, render, screen, waitFor } = rtlModule.default ?? rtlModule

const requests = []
let responses = []
let params = { id: '42' }
let searchParams = new URLSearchParams()
const graphqlRequest = async (operation, variables) => {
  requests.push({ operation, variables })
  if (!responses.length) throw new Error('No mocked GraphQL response')
  const response = responses.shift()
  if (response instanceof Error) throw response
  return typeof response === 'function' ? response() : response
}
const gql = (parts, ...values) => parts.reduce((text, part, index) => text + part + (values[index] ?? ''), '')

vi.doMock('@/lib/graphql', () => ({ graphqlRequest, gql }))
vi.doMock('next/navigation', () => ({ useParams: () => params, useSearchParams: () => searchParams }))
vi.doMock('@/components/DataTable', () => ({
  default: ({ columns, data, loading, rowHref, addHref, addLabel, onDelete, emptyMessage }) => React.createElement(
    'section',
    { 'data-testid': 'table', 'data-loading': String(Boolean(loading)) },
    addHref && React.createElement('a', { href: addHref }, addLabel),
    !loading && data.length === 0 && React.createElement('p', null, emptyMessage),
    data.map((row) => React.createElement(
      'div',
      { key: row.id, 'data-testid': `row-${row.id}`, 'data-href': rowHref?.(row) ?? '' },
      columns.map((column) => React.createElement('span', { key: column.key }, String(column.accessor(row)))),
      onDelete && React.createElement(
        'button',
        { type: 'button', onClick: () => void onDelete(row), name: `delete-${row.id}` },
        `delete-${row.id}`,
      ),
    )),
  ),
}))
vi.doMock('@/components/EntityForm', () => ({
  default: ({ title, backHref, onSave, onDelete, saving, fieldsets }) => React.createElement(
    'form',
    { onSubmit: (event) => { event.preventDefault(); void onSave() }, 'data-saving': String(Boolean(saving)) },
    React.createElement('h1', null, title),
    React.createElement('a', { href: backHref }, 'Back'),
    fieldsets.map((fieldset) => React.createElement('fieldset', { key: fieldset.title }, React.createElement('legend', null, fieldset.title), fieldset.content)),
    React.createElement('button', { type: 'submit' }, 'Save'),
    onDelete && React.createElement('button', { type: 'button', onClick: () => void onDelete() }, 'Delete'),
  ),
}))
const input = (type = 'text') => {
  function MockInput({ label, name, value, checked, onChange, options = [], helpText, ...props }) {
    return React.createElement(
      'label',
      null,
      label,
      type === 'select'
        ? React.createElement('select', { 'aria-label': label, name, value, onChange: (event) => onChange(name, event.target.value), ...props }, options.map((option) => React.createElement('option', { key: option.value, value: option.value }, option.label)))
        : React.createElement('input', { 'aria-label': label, name, type, value: type === 'checkbox' ? undefined : value, checked: type === 'checkbox' ? checked : undefined, onChange: (event) => onChange(name, type === 'checkbox' ? event.target.checked : event.target.value), ...props }),
      helpText && React.createElement('small', null, helpText),
    )
  }
  return MockInput
}
vi.doMock('@/components/FormField', () => ({
    FormField: input(),
    SelectField: input('select'),
    TextareaField: input(),
    CheckboxField: input('checkbox'),
    ReadonlyField: ({ label, value }) => React.createElement('output', { 'aria-label': label }, String(value)),
}))

const DaysPage = (await import('../src/app/days/page.tsx')).default
const EditDayPage = (await import('../src/app/days/[id]/page.tsx')).default
const IntakesPage = (await import('../src/app/intakes/page.tsx')).default
const NewIntakePage = (await import('../src/app/intakes/new/page.tsx')).default
const EditIntakePage = (await import('../src/app/intakes/[id]/page.tsx')).default
const ExercisesPage = (await import('../src/app/exercises/page.tsx')).default
const NewExercisePage = (await import('../src/app/exercises/new/page.tsx')).default
const EditExercisePage = (await import('../src/app/exercises/[id]/page.tsx')).default
const GoalsPage = (await import('../src/app/goals/page.tsx')).default
const NewGoalPage = (await import('../src/app/goals/new/page.tsx')).default
const EditGoalPage = (await import('../src/app/goals/[id]/page.tsx')).default
const PlansPage = (await import('../src/app/plans/page.tsx')).default
const NewPlanPage = (await import('../src/app/plans/new/page.tsx')).default
const EditPlanPage = (await import('../src/app/plans/[id]/page.tsx')).default
const MeasurementsPage = (await import('../src/app/measurements/page.tsx')).default
const NewMeasurementPage = (await import('../src/app/measurements/new/page.tsx')).default
const EditMeasurementPage = (await import('../src/app/measurements/[id]/page.tsx')).default
const StepsPage = (await import('../src/app/steps/page.tsx')).default
const NewStepsPage = (await import('../src/app/steps/new/page.tsx')).default
const EditStepsPage = (await import('../src/app/steps/[id]/page.tsx')).default

afterEach(() => {
  cleanup()
  requests.length = 0
  responses = []
  params = { id: '42' }
  searchParams = new URLSearchParams()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

const deferred = () => {
  let resolve, reject
  const promise = new Promise((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

const waitForTableLoaded = async () => waitFor(() => {
  assert.equal(screen.getByTestId('table').dataset.loading, 'false')
})

const waitForEditLoaded = async () => waitFor(() => {
  assert.equal(screen.queryByText('Loading...'), null)
})

test('list loaders cancel pending fulfillment and rejection after unmount', async () => {
  const pendingPlan = deferred()
  responses = [() => pendingPlan.promise]
  const planView = render(React.createElement(PlansPage))
  planView.unmount()
  pendingPlan.resolve({ weekPlans: [] })

  const pendingExercises = deferred()
  responses = [() => pendingExercises.promise]
  const exerciseView = render(React.createElement(ExercisesPage))
  exerciseView.unmount()
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  pendingExercises.reject(new Error('cancelled request'))

  await new Promise(setImmediate)
  assert.equal(
    consoleError.mock.calls.some((call) => call[0] === 'Failed to fetch exercises'),
    false,
  )
})

test('plans list renders success rows, empty state, and fetch failures', async () => {
  responses = [{
    weekPlans: [
      { id: 'p2', startDate: '2026-03-02', completed: true, energyKcalGoal: 190.6, energyKcal: 195.3 },
      { id: 'p1', startDate: '2026-03-01', completed: false, energyKcalGoal: 200.9, energyKcal: 198.4 },
    ],
  }]
  render(React.createElement(PlansPage))
  assert.equal(screen.getByTestId('table').dataset.loading, 'true')
  await waitForTableLoaded()
  assert.equal(screen.getByTestId('row-p2').dataset.href, '/plans/p2')
  assert.equal(screen.getByText('Week Plans').textContent, 'Week Plans')

  const planError = new Error('plans failed')
  cleanup()
  requests.length = 0
  responses = [{ weekPlans: [] }]
  render(React.createElement(PlansPage))
  await screen.findByText('No plans created yet.')
  cleanup()
  requests.length = 0
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  responses = [planError]
  render(React.createElement(PlansPage))
  await waitForTableLoaded()
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to fetch plans', planError])
})

test('plan creation submits parsed fields and preserves saving state', async () => {
  const pending = deferred()
  responses = [() => pending.promise]
  render(React.createElement(NewPlanPage))
  fireEvent.change(screen.getByLabelText('Measurement ID'), { target: { value: '17' } })
  fireEvent.change(screen.getByLabelText('Protein (g/kg)'), { target: { value: '2.4' } })
  fireEvent.change(screen.getByLabelText('Fat (%)'), { target: { value: '25.5' } })
  fireEvent.change(screen.getByLabelText('Deficit (kcals)'), { target: { value: '350' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'true'))
  assert.deepEqual(requests[0].variables, {
    startDate: requests[0].variables.startDate,
    proteinGKg: 2.4,
    fatPerc: 25.5,
    deficit: 350,
    measurementId: 17,
  })
  pending.resolve({ createWeekPlan: { id: 'p3' } })
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'false'))
})

test('plan edit saves, deletes, handles missing payload, and logs fetch failures', async () => {
  const updatePending = deferred()
  responses = [{
    weekPlan: {
      id: 'p42',
      startDate: '2026-01-01',
      proteinGKg: 2,
      fatPerc: 20,
      deficit: 300,
      twee: 1500,
      completed: false,
      energyKcalGoal: 210.2,
      energyKcal: 199.8,
      days: [
        { id: 'd9', day: '2026-01-01', dayNum: 1, completed: true, energyKcalGoal: 250.1, energyKcal: 220.9 },
        { id: 'd10', day: '2026-01-02', dayNum: 2, completed: false, energyKcalGoal: 250.1, energyKcal: 200.1 },
      ],
    },
  }, () => updatePending.promise, {}]
  render(React.createElement(EditPlanPage))
  await waitForEditLoaded()
  fireEvent.change(screen.getByLabelText('Protein (g/kg)'), { target: { value: '1.9' } })
  fireEvent.change(screen.getByLabelText('Fat (%)'), { target: { value: '22.5' } })
  fireEvent.change(screen.getByLabelText('Deficit (kcals)'), { target: { value: '250' } })
  fireEvent.submit(document.querySelector('form'))
  assert.deepEqual(requests[1].variables, { id: '42', proteinGKg: 1.9, fatPerc: 22.5, deficit: 250 })
  updatePending.resolve({ updateWeekPlan: { id: 'p42' } })
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'false'))
  fireEvent.click(screen.getByText('Delete'))
  assert.deepEqual(requests[2].variables, { id: '42' })
  cleanup()
  requests.length = 0
  responses = [{ weekPlan: null }, { updateWeekPlan: { id: 'p42' } }]
  render(React.createElement(EditPlanPage))
  await waitForEditLoaded()
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests.length, 2))
  assert.equal(requests[1].variables.id, '42')
  assert.equal(Object.prototype.hasOwnProperty.call(requests[1].variables, 'proteinGKg'), true)

  const planError = new Error('plan failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  cleanup()
  requests.length = 0
  responses = [planError]
  render(React.createElement(EditPlanPage))
  await waitForEditLoaded()
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to fetch plan', planError])
})

test('days list renders loading, sorted rows, empty state, and request errors', async () => {
  responses = [{ weekPlans: [{ days: [
    { id: '1', day: '2026-01-01', completed: false, energyKcal: 99.5, energyKcalGoal: 200.4 },
    { id: '2', day: '2026-02-01', completed: true, energyKcal: 101.6, energyKcalGoal: 300.5 },
  ] }] }]
  render(React.createElement(DaysPage))
  assert.equal(screen.getByTestId('table').dataset.loading, 'true')
  await waitForTableLoaded()
  assert.equal(screen.getAllByTestId(/^row-/)[0].dataset.href, '/days/2')
  assert.match(screen.getByTestId('row-1').textContent, /No100 \/ 200 kcal/)
  assert.match(screen.getByTestId('row-2').textContent, /Yes102 \/ 301 kcal/)
  cleanup()
  requests.length = 0
  responses = [{ weekPlans: [] }]
  render(React.createElement(DaysPage))
  await screen.findByText('No days available yet.')
  cleanup()
  requests.length = 0
  const error = new Error('days failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  responses = [error]
  render(React.createElement(DaysPage))
  await waitForTableLoaded()
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to fetch days', error])
})

test('day edit updates tracked flag, handles missing day, and logs fetch failures', async () => {
  responses = [{
    day: {
      id: '1',
      planId: 'p7',
      day: '2026-01-10',
      dayNum: 2,
      deficit: 500,
      tracked: false,
      completed: true,
      energyKcalGoal: 200.5,
      energyKcal: 190.4,
      proteinGGoal: 150,
      proteinG: 123.5,
      fatGGoal: 50,
      fatG: 49.5,
      carbsGGoal: 250.1,
      carbsG: 250.7,
      tdee: 2100,
      intakes: [{ id: 'i1', meal: 'breakfast', numServings: 2, energyKcal: 500, proteinG: 20, fatG: 10 }],
    },
  }, { updateDay: { id: '1' } }]
  render(React.createElement(EditDayPage))
  await waitForEditLoaded()
  fireEvent.click(screen.getByRole('checkbox', { name: 'Tracked' }))
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests[1].variables.id, '42'))
  assert.deepEqual(requests[1].variables, { id: '42', tracked: true })
  assert.equal(screen.getByTestId('row-i1').dataset.href, '/intakes/i1')
  cleanup()
  requests.length = 0
  responses = [{ day: null }, { updateDay: { id: '1' } }]
  render(React.createElement(EditDayPage))
  await waitForEditLoaded()
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests[1].variables.id, '42'))
  assert.equal(requests[1].variables.tracked, false)

  const dayError = new Error('day failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  cleanup()
  requests.length = 0
  responses = [dayError]
  render(React.createElement(EditDayPage))
  await waitForEditLoaded()
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to fetch day', dayError])
})

test('exercise list renders all cells and covers cancelled, successful, and failed deletion', async () => {
  const rows = [
    { id: 'e1', type: 'run', kcals: 100, duration: null, distance: null, time: '08:00' },
    { id: 'e2', type: 'walk', kcals: 50, duration: '00:30:00', distance: 0, time: '09:00' },
  ]
  responses = [{ exercises: rows }]
  const confirmMock = vi.spyOn(globalThis, 'confirm').mockImplementation(() => false)
  render(React.createElement(ExercisesPage))
  await screen.findByTestId('row-e1')
  assert.match(screen.getByTestId('row-e1').textContent, /Run100——08:00/)
  assert.match(screen.getByTestId('row-e2').textContent, /Walk5000:30:00009:00/)
  fireEvent.click(screen.getByText('delete-e1'))
  assert.equal(requests.length, 1)

  confirmMock.mockImplementation(() => true)
  responses = [undefined, { exercises: [rows[1]] }]
  await act(async () => {
    fireEvent.click(screen.getByText('delete-e1'))
    await new Promise(setImmediate)
  })
  assert.equal(screen.queryByTestId('row-e1'), null)
  assert.deepEqual(requests[1].variables, { id: 'e1' })

  const error = new Error('delete failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  responses = [error]
  await act(async () => {
    fireEvent.click(screen.getByText('delete-e2'))
    await new Promise(setImmediate)
  })
  assert.equal(consoleError.mock.calls.length, 1)
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to delete exercise', error])
})

test('new exercise submits parsed required and optional fields', async () => {
  const pending = deferred()
  responses = [() => pending.promise, { createExercise: { id: 'e4' } }]
  render(React.createElement(NewExercisePage))
  fireEvent.change(screen.getByLabelText('Day ID'), { target: { value: '9' } })
  fireEvent.change(screen.getByLabelText('Kcals'), { target: { value: '450' } })
  fireEvent.change(screen.getByLabelText('Time'), { target: { value: '07:30' } })
  fireEvent.change(screen.getByLabelText('Duration (hh:mm:ss)'), { target: { value: '' } })
  fireEvent.change(screen.getByLabelText('Distance (km)'), { target: { value: '' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'true'))
  assert.deepEqual(requests[0].variables, {
    dayId: 9,
    type: 'walk',
    kcals: 450,
    time: '07:30',
    duration: null,
    distance: null,
  })
  pending.resolve({ createExercise: { id: 'e3' } })
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'false'))
  fireEvent.change(screen.getByLabelText('Time'), { target: { value: '' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests.length, 2))
  assert.equal(requests[1].variables.time, '00:00')
})

test('edit exercise loads values, submits payloads, deletes, and handles missing/exceptions', async () => {
  responses = [{
    exercise: {
      id: 'e99',
      dayId: 8,
      time: '08:45',
      type: 'run',
      kcals: 300,
      duration: '00:20:00',
      distance: null,
    },
  }, { updateExercise: { id: 'e99' } }, {}]
  render(React.createElement(EditExercisePage))
  await waitForEditLoaded()
  fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'cycle' } })
  fireEvent.change(screen.getByLabelText('Kcals'), { target: { value: '250' } })
  fireEvent.change(screen.getByLabelText('Distance (km)'), { target: { value: '' } })
  fireEvent.change(screen.getByLabelText('Time'), { target: { value: '' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests[1].variables.id, '42'))
  assert.deepEqual(requests[1].variables, {
    id: '42',
    type: 'cycle',
    kcals: 250,
    time: '00:00',
    duration: '00:20:00',
    distance: null,
  })
  fireEvent.click(screen.getByText('Delete'))
  assert.deepEqual(requests[2].variables, { id: '42' })
  cleanup()
  requests.length = 0
  responses = [{ exercise: null }]
  render(React.createElement(EditExercisePage))
  await waitFor(() => assert.ok(screen.getByText('Exercise not found.')))
  assert.equal(requests.length, 1)
  assert.equal(document.querySelector('form'), null)

  const exerciseError = new Error('exercise failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  cleanup()
  requests.length = 0
  responses = [exerciseError]
  render(React.createElement(EditExercisePage))
  await waitFor(() => assert.ok(screen.getByText('Unable to load exercise.')))
  assert.equal(document.querySelector('form'), null)
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to fetch exercise', exerciseError])
})

test('exercise list covers empty and load error results', async () => {
  responses = [{ exercises: [] }]
  const view = render(React.createElement(ExercisesPage))
  await screen.findByText('No exercises logged yet.')
  view.unmount()

  const error = new Error('load failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  responses = [error]
  render(React.createElement(ExercisesPage))
  await waitForTableLoaded()
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to fetch exercises', error])
})

test('goal list renders formatted values and covers deletion branches and load failures', async () => {
  const row = { id: 'g1', bodyFatPerc: 18.5, createdAt: '2026-01-02T00:00:00Z' }
  responses = [{ fatPercGoals: [row] }]
  const confirmMock = vi.spyOn(globalThis, 'confirm').mockImplementation(() => false)
  render(React.createElement(GoalsPage))
  await screen.findByTestId('row-g1')
  assert.equal(screen.getByTestId('row-g1').dataset.href, '/goals/g1')
  assert.match(screen.getByTestId('row-g1').textContent, /18.5/)
  fireEvent.click(screen.getByText('delete-g1'))
  assert.equal(requests.length, 1)

  confirmMock.mockImplementation(() => true)
  responses = [undefined, { fatPercGoals: [] }]
  fireEvent.click(screen.getByText('delete-g1'))
  await screen.findByText('No goals set yet. Add your first one!')

  const error = new Error('goal delete failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  responses = [{ fatPercGoals: [row] }, error]
  cleanup()
  requests.length = 0
  render(React.createElement(GoalsPage))
  await screen.findByTestId('row-g1')
  fireEvent.click(screen.getByText('delete-g1'))
  await waitFor(() => assert.deepEqual(consoleError.mock.calls[0], ['Failed to delete goal', error]))
  cleanup()
  requests.length = 0

  responses = [new Error('goal load failed')]
  render(React.createElement(GoalsPage))
  await waitForTableLoaded()
  assert.equal(consoleError.mock.calls.length, 2)
})

test('new goal updates its field and submits parsed variables while showing saving state', async () => {
  const pending = deferred()
  responses = [() => pending.promise]
  render(React.createElement(NewGoalPage))
  fireEvent.change(screen.getByLabelText('Body Fat % Goal'), { target: { value: '17.25' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'true'))
  assert.deepEqual(requests[0].variables, { bodyFatPerc: 17.25 })
  pending.resolve({ createFatPercGoal: { id: 'g2' } })
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'false'))
})

test('edit goal updates, deletes, handles missing state, and logs fetch failures', async () => {
  responses = [{ fatPercGoal: { id: 'g1', bodyFatPerc: 18.5, createdAt: '2026-01-02T00:00:00Z' } }, { updateFatPercGoal: { id: 'g1' } }, {}]
  render(React.createElement(EditGoalPage))
  await waitForEditLoaded()
  fireEvent.change(screen.getByLabelText('Body Fat % Goal'), { target: { value: '19.2' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests.length >= 2, true))
  assert.equal(requests[1].variables.id, '42')
  assert.equal(requests[1].variables.bodyFatPerc, 19.2)
  fireEvent.click(screen.getByText('Delete'))
  await waitFor(() => assert.equal(requests[2].variables.id, '42'))
  cleanup()
  requests.length = 0
  responses = [{ fatPercGoal: null }]
  render(React.createElement(EditGoalPage))
  await waitFor(() => assert.ok(screen.getByText('Goal not found.')))
  assert.equal(requests.length, 1)
  assert.equal(document.querySelector('form'), null)

  cleanup()
  requests.length = 0
  responses = [{ fatPercGoal: { id: 'g1', bodyFatPerc: 18.5, createdAt: '' } }]
  render(React.createElement(EditGoalPage))
  await waitForEditLoaded()
  assert.equal(screen.getByLabelText('Created At').textContent, '—')

  const goalError = new Error('goal fetch failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  cleanup()
  requests.length = 0
  responses = [goalError]
  render(React.createElement(EditGoalPage))
  await waitFor(() => assert.ok(screen.getByText('Unable to load goal.')))
  assert.equal(document.querySelector('form'), null)
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to fetch goal', goalError])
})

test('intakes list is static guidance', async () => {
  render(React.createElement(IntakesPage))
  await screen.findByText('Please browse to a specific Plan > Day to view and manage intakes.')
})

test('new intake submits parsed custom macro fields', async () => {
  const pending = deferred()
  responses = [() => pending.promise]
  render(React.createElement(NewIntakePage))
  fireEvent.change(screen.getByLabelText('Day ID'), { target: { value: '11' } })
  fireEvent.change(screen.getByLabelText('Number of Servings'), { target: { value: '2.5' } })
  fireEvent.change(screen.getByLabelText('Energy (kcal)'), { target: { value: '250.5' } })
  fireEvent.change(screen.getByLabelText('Protein (g)'), { target: { value: '20.1' } })
  fireEvent.change(screen.getByLabelText('Fat (g)'), { target: { value: '' } })
  fireEvent.change(screen.getByLabelText('Carbs (g)'), { target: { value: '' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'true'))
  assert.deepEqual(requests[0].variables, {
    dayId: 11,
    meal: 'breakfast',
    numServings: 2.5,
    energyKcal: 250.5,
    proteinG: 20.1,
    fatG: 0,
    carbsG: 0,
  })
  pending.resolve({ createIntake: { id: 'i10' } })
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'false'))

  // A dayId supplied via the query string pre-fills the form and is submitted as an int.
  cleanup()
  requests.length = 0
  searchParams = new URLSearchParams([['dayId', '7']])
  responses = [{ createIntake: { id: 'i11' } }]
  render(React.createElement(NewIntakePage))
  await waitFor(() => assert.equal(screen.getByLabelText('Day ID').value, '7'))
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests.length, 1))
  assert.equal(requests[0].variables.dayId, 7)
})

test('edit intake covers food-backed and custom branches and missing payload branch', async () => {
  responses = [{
    intake: {
      id: 'i1',
      dayId: '9',
      foodId: 'f1',
      meal: 'breakfast',
      numServings: 2,
      energyKcal: 500,
      proteinG: 40,
      fatG: 20,
    carbsG: 30,
  },
  }, { updateIntake: { id: 'i1' } }]
  render(React.createElement(EditIntakePage))
  await waitForEditLoaded()
  fireEvent.change(screen.getByLabelText('Meal'), { target: { value: 'lunch' } })
  fireEvent.change(screen.getByLabelText('Number of Servings'), { target: { value: '3' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests[1].variables.id, '42'))
  assert.deepEqual(requests[1].variables, {
    id: '42',
    meal: 'lunch',
    numServings: 3,
    energyKcal: 500,
    proteinG: 40,
    fatG: 20,
    carbsG: 30,
  })
  cleanup()
  requests.length = 0
  responses = [{
    intake: {
      id: 'i-empty', dayId: '9', foodId: 'f1', meal: 'lunch', numServings: 1,
      energyKcal: '', proteinG: '', fatG: '', carbsG: '',
    },
  }, { updateIntake: { id: 'i-empty' } }]
  render(React.createElement(EditIntakePage))
  await waitForEditLoaded()
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests.length, 2))
  assert.equal(requests[1].variables.energyKcal, 0)
  assert.equal(requests[1].variables.proteinG, 0)
  assert.equal(requests[1].variables.fatG, 0)
  assert.equal(requests[1].variables.carbsG, 0)
  cleanup()
  requests.length = 0
  responses = [{
    intake: {
      id: 'i2',
      dayId: '9',
      foodId: null,
      meal: 'snack',
      numServings: 1.5,
      energyKcal: 120,
      proteinG: 10,
      fatG: 5,
    carbsG: 8,
  },
  }, { updateIntake: { id: 'i2' } }]
  render(React.createElement(EditIntakePage))
  await waitForEditLoaded()
  fireEvent.change(screen.getByLabelText('Energy (kcal)'), { target: { value: '200' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests[1].variables.id, '42'))
  assert.deepEqual(requests[1].variables, {
    id: '42',
    meal: 'snack',
    numServings: 1.5,
    energyKcal: 200,
    proteinG: 10,
    fatG: 5,
    carbsG: 8,
  })
  cleanup()
  requests.length = 0
  responses = [{ intake: null }, { updateIntake: { id: 'i3' } }]
  render(React.createElement(EditIntakePage))
  await waitForEditLoaded()
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests.length, 2))
  assert.equal(requests[1].variables.id, '42')

  const intakeError = new Error('intake failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  cleanup()
  requests.length = 0
  responses = [intakeError]
  render(React.createElement(EditIntakePage))
  await waitForEditLoaded()
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to fetch intake', intakeError])
})

test('measurements list loads rows and handles delete and fetch errors', async () => {
  const row = { id: 'm1', bodyFatPerc: 18.8, weight: 82.4, bmr: 1650.9, createdAt: '2026-01-01T00:00:00Z' }
  const error = new Error('measurement load failed')
  const deleteError = new Error('measurement delete failed')
  responses = [{ measurements: [{
    id: 'm1',
    bodyFatPerc: 18.8,
    weight: 82.4,
    bmr: 1650.9,
    createdAt: '2026-01-01T00:00:00Z',
  }, {
    id: 'm0',
    bodyFatPerc: null,
    weight: 81.9,
    bmr: null,
    createdAt: '2025-12-31T00:00:00Z',
  }] }]
  render(React.createElement(MeasurementsPage))
  await waitForTableLoaded()
  assert.equal(screen.getByTestId('row-m1').dataset.href, '/measurements/m1')
  assert.equal((screen.getByTestId('row-m0').textContent.match(/—/g) ?? []).length, 2)
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  const confirmMock = vi.spyOn(globalThis, 'confirm').mockImplementation(() => false)
  fireEvent.click(screen.getByText('delete-m1'))
  assert.equal(requests.length, 1)
  confirmMock.mockImplementation(() => true)
  responses = [undefined, { measurements: [] }]
  fireEvent.click(screen.getByText('delete-m1'))
  await screen.findByText('No measurements yet. Add your first one!')
  assert.deepEqual(requests[1].variables, { id: 'm1' })
  cleanup()
  requests.length = 0
  responses = [{ measurements: [row] }, deleteError]
  render(React.createElement(MeasurementsPage))
  await screen.findByText('delete-m1')
  await act(async () => {
    fireEvent.click(screen.getByText('delete-m1'))
    await new Promise(setImmediate)
  })
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to delete measurement', deleteError])
  cleanup()
  requests.length = 0
  responses = [error]
  render(React.createElement(MeasurementsPage))
  await waitForTableLoaded()
  assert.deepEqual(consoleError.mock.calls[1], ['Failed to fetch measurements', error])
})

test('measurements page renders the reusable trend chart and validates custom date ranges', async () => {
  const measurements = Array.from({ length: 20 }, (_, index) => ({
    id: `m${index + 1}`,
    bodyFatPerc: 20 - index / 10,
    weight: 81 - index / 10,
    bmr: 1600 + index,
    createdAt: new Date(2026, 0, index + 1, 12).toISOString(),
  }))
  responses = [{ measurements }]
  render(React.createElement(MeasurementsPage))
  await waitForTableLoaded()
  assert.equal(requests.length, 1)
  assert.match(document.body.textContent, /Showing measurements for:/)
  assert.match(document.body.textContent, /No measurements found for this date range/)

  const rangeSelect = screen.getByLabelText('Trend range')
  fireEvent.change(rangeSelect, { target: { value: 'lastQuarter' } })
  assert.match(document.body.textContent, /Showing measurements for: Last quarter/)
  fireEvent.change(rangeSelect, { target: { value: 'lastYear' } })
  assert.match(document.body.textContent, /Showing measurements for: Last year/)
  fireEvent.change(rangeSelect, { target: { value: 'custom' } })

  fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '' } })
  assert.equal(
    (await screen.findByRole('alert')).textContent,
    'Pick both a start and end date to use a custom range.',
  )

  fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-01-20' } })
  fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-01-01' } })

  const rangeError = await screen.findByRole('alert')
  assert.equal(rangeError.textContent, 'Start date must be on or before end date.')
  assert.equal(screen.getAllByText('Start date must be on or before end date.').length, 1)
  assert.equal(screen.queryByRole('link', { name: 'Log weight →' }), null)
  assert.equal(screen.getByLabelText('Start date').getAttribute('aria-invalid'), 'true')
  assert.equal(screen.getByLabelText('End date').getAttribute('aria-invalid'), 'true')

  fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-01-01' } })
  fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-01-20' } })
  assert.equal(screen.getByLabelText('Start date').getAttribute('aria-invalid'), 'false')
  assert.equal(screen.getByLabelText('End date').getAttribute('aria-invalid'), 'false')
  await screen.findByText('Weight trend')
  assert.ok(screen.getByRole('img', { name: /Weight trend from 81 kilograms to 79.1 kilograms/ }))
  const trendDots = screen.getAllByTestId('weight-trend-dot')
  const accessibleTrendDots = screen.getAllByRole('img', { name: /Measurement on .*: .* kilograms/ })
  assert.equal(trendDots.length, 20)
  assert.equal(accessibleTrendDots.length, 20)
  assert.equal(document.querySelectorAll('svg circle').length, 0)
  assert.ok(trendDots.every((dot) => dot.classList.contains('rounded-full')))
  assert.ok(trendDots.every((dot) => dot.classList.contains('size-2.5')))
  assert.ok(trendDots.every((dot) => dot.classList.contains('cursor-help')))
  assert.ok(trendDots.every((dot) => dot.tabIndex === 0))
  assert.ok(trendDots.every((dot) => dot.style.left.endsWith('%') && dot.style.top.endsWith('%')))
  assert.equal(screen.queryByRole('tooltip'), null)
  const interactionRegion = screen.getByTestId('weight-trend-interaction')

  fireEvent.mouseEnter(trendDots[0])
  const hoveredTooltip = screen.getByRole('tooltip')
  assert.equal(hoveredTooltip.textContent, '2026-01-01: 81 kg')
  assert.equal(trendDots[0].getAttribute('aria-describedby'), hoveredTooltip.id)
  assert.ok(hoveredTooltip.classList.contains('w-full'))
  assert.equal(hoveredTooltip.classList.contains('absolute'), false)
  fireEvent.mouseEnter(hoveredTooltip)
  assert.equal(screen.getByRole('tooltip').textContent, '2026-01-01: 81 kg')
  fireEvent.keyDown(window, { key: 'ArrowRight' })
  assert.ok(screen.getByRole('tooltip'))
  fireEvent.keyDown(window, { key: 'Escape' })
  assert.equal(screen.queryByRole('tooltip'), null)

  fireEvent.mouseEnter(trendDots[0])
  fireEvent.mouseLeave(interactionRegion)
  assert.equal(screen.queryByRole('tooltip'), null)

  act(() => trendDots[0].focus())
  assert.equal(document.activeElement, trendDots[0])
  fireEvent.mouseEnter(trendDots.at(-1))
  assert.equal(screen.getByRole('tooltip').textContent, '2026-01-20: 79.1 kg')
  fireEvent.mouseLeave(interactionRegion)
  assert.equal(screen.getByRole('tooltip').textContent, '2026-01-01: 81 kg')
  fireEvent.blur(trendDots[0], { relatedTarget: trendDots.at(-1) })
  act(() => trendDots.at(-1).focus())
  const focusedTooltip = screen.getByRole('tooltip')
  assert.equal(focusedTooltip.textContent, '2026-01-20: 79.1 kg')
  assert.equal(trendDots.at(-1).getAttribute('aria-describedby'), focusedTooltip.id)
  fireEvent.blur(trendDots.at(-1), { relatedTarget: document.body })
  assert.equal(screen.queryByRole('tooltip'), null)

  fireEvent.mouseEnter(trendDots.at(-1))
  fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-01-19' } })
  assert.equal(screen.queryByRole('tooltip'), null)
  fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-01-20' } })
  assert.equal(screen.queryByRole('tooltip'), null)
  assert.equal(requests.length, 1)
})

test('measurements preset ranges roll forward at local midnight', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2026, 0, 31, 23, 59, 59, 900))
  responses = [{ measurements: [
    { id: 'jan-2', bodyFatPerc: 20, weight: 70, bmr: 1600, createdAt: new Date(2026, 0, 2, 12).toISOString() },
    { id: 'jan-31', bodyFatPerc: 19.8, weight: 69, bmr: 1605, createdAt: new Date(2026, 0, 31, 12).toISOString() },
    { id: 'feb-1', bodyFatPerc: 19.6, weight: 68, bmr: 1598, createdAt: new Date(2026, 1, 1, 0).toISOString() },
  ] }]

  render(React.createElement(MeasurementsPage))
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
  assert.ok(screen.getByRole('img', { name: /Weight trend from 70 kilograms to 69 kilograms/ }))

  await act(async () => {
    await vi.advanceTimersByTimeAsync(200)
  })
  assert.ok(screen.getByRole('img', { name: /Weight trend from 69 kilograms to 68 kilograms/ }))
})

test('new measurement submits optional body fat without preloading it', async () => {
  const pending = deferred()
  responses = [() => pending.promise]
  render(React.createElement(NewMeasurementPage))
  assert.equal(screen.getByLabelText('Body Fat (%)').value, '')
  assert.equal(requests.length, 0)
  fireEvent.change(screen.getByLabelText('Body Fat (%)'), { target: { value: '18.2' } })
  fireEvent.change(screen.getByLabelText('Weight (kg)'), { target: { value: '81.5' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'true'))
  assert.deepEqual(requests[0].variables, { bodyFatPerc: 18.2, weight: 81.5 })
  pending.resolve({ createMeasurement: { id: 'm2' } })
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'false'))

  cleanup()
  requests.length = 0
  responses = [{ createMeasurement: { id: 'm3' } }]
  render(React.createElement(NewMeasurementPage))
  fireEvent.change(screen.getByLabelText('Weight (kg)'), { target: { value: '80' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests.length, 1))
  assert.deepEqual(requests[0].variables, { bodyFatPerc: null, weight: 80 })
})

test('edit measurement covers success, missing, and fetch failures', async () => {
  cleanup()
  requests.length = 0
  responses = [{
    measurement: {
      id: 'm1',
      bodyFatPerc: 19.1,
      weight: 82.3,
      bmr: 1650.8,
      createdAt: '2026-01-03T00:00:00Z',
    },
  }, { updateMeasurement: { id: 'm1' } }, {}]
  render(React.createElement(EditMeasurementPage))
  await waitForEditLoaded()
  fireEvent.change(screen.getByLabelText('Body Fat (%)'), { target: { value: '19.9' } })
  fireEvent.change(screen.getByLabelText('Weight (kg)'), { target: { value: '80.0' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests[1].variables.id, '42'))
  assert.equal(requests[1].variables.id, '42')
  assert.equal(requests[1].variables.bodyFatPerc, 19.9)
  fireEvent.click(screen.getByText('Delete'))
  assert.equal(requests[2].variables.id, '42')
  cleanup()
  requests.length = 0
  responses = [{ measurement: null }]
  render(React.createElement(EditMeasurementPage))
  await waitFor(() => assert.ok(screen.getByText('Measurement not found.')))
  assert.equal(requests.length, 1)
  assert.equal(document.querySelector('form'), null)

  cleanup()
  requests.length = 0
  responses = [{
    measurement: {
      id: 'm1', bodyFatPerc: null, weight: 82.3, bmr: null, createdAt: '',
    },
  }]
  render(React.createElement(EditMeasurementPage))
  await waitForEditLoaded()
  assert.equal(screen.getByLabelText('Body Fat (%)').value, '')
  assert.equal(screen.getByLabelText('BMR').textContent, '—')
  assert.equal(screen.getByLabelText('Created At').textContent, '—')

  const measurementError = new Error('measurement failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  cleanup()
  requests.length = 0
  responses = [measurementError]
  render(React.createElement(EditMeasurementPage))
  await waitFor(() => assert.ok(screen.getByText('Unable to load measurement.')))
  assert.equal(document.querySelector('form'), null)
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to fetch measurement', measurementError])
})

test('steps list loads rows and covers delete and load failure branches', async () => {
  responses = [{ dayStepsList: [{ id: 's1', dayId: 2, steps: 1234, kcals: 43.1 }] }]
  render(React.createElement(StepsPage))
  await waitForTableLoaded()
  assert.equal(screen.getByTestId('row-s1').dataset.href, '/steps/s1')
  assert.match(screen.getByTestId('row-s1').textContent, /1,234/)
  const confirmMock = vi.spyOn(globalThis, 'confirm').mockImplementation(() => false)
  fireEvent.click(screen.getByText('delete-s1'))
  assert.equal(requests.length, 1)
  confirmMock.mockImplementation(() => true)
  responses = [undefined, { dayStepsList: [] }]
  fireEvent.click(screen.getByText('delete-s1'))
  await screen.findByText('No step records yet.')
  assert.deepEqual(requests[1].variables, { id: 's1' })

  const error = new Error('steps failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  cleanup()
  requests.length = 0
  responses = [error]
  render(React.createElement(StepsPage))
  await waitForTableLoaded()
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to fetch steps', error])
})

test('new and edit steps submit parsed ints and cover missing/dayless branch', async () => {
  const pending = deferred()
  responses = [() => pending.promise]
  render(React.createElement(NewStepsPage))
  fireEvent.change(screen.getByLabelText('Day ID'), { target: { value: '4' } })
  fireEvent.change(screen.getByLabelText('Steps'), { target: { value: '10000' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'true'))
  assert.deepEqual(requests[0].variables, { dayId: 4, steps: 10000 })
  pending.resolve({ createDaySteps: { id: 's2' } })
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'false'))
  cleanup()
  requests.length = 0
  responses = [{ daySteps: { id: 's2', steps: 1500, kcals: 55 } }, { updateDaySteps: { id: 's2' } }, {}]
  render(React.createElement(EditStepsPage))
  await waitForEditLoaded()
  fireEvent.change(screen.getByLabelText('Steps'), { target: { value: '2000' } })
  fireEvent.submit(document.querySelector('form'))
  assert.deepEqual(requests[1].variables, { id: '42', steps: 2000 })
  fireEvent.click(screen.getByText('Delete'))
  assert.deepEqual(requests[2].variables, { id: '42' })
  cleanup()
  requests.length = 0
  responses = [{ daySteps: null }]
  render(React.createElement(EditStepsPage))
  await waitFor(() => assert.ok(screen.getByText('Steps not found.')))
  assert.equal(requests.length, 1)
  assert.equal(document.querySelector('form'), null)

  cleanup()
  requests.length = 0
  responses = [{ daySteps: { id: 's2', steps: 1500, kcals: null } }]
  render(React.createElement(EditStepsPage))
  await waitForEditLoaded()
  assert.equal(screen.getByLabelText('Kcals').textContent, '—')

  const stepError = new Error('steps failed')
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  cleanup()
  requests.length = 0
  responses = [stepError]
  render(React.createElement(EditStepsPage))
  await waitFor(() => assert.ok(screen.getByText('Unable to load steps.')))
  assert.equal(document.querySelector('form'), null)
  assert.deepEqual(consoleError.mock.calls[0], ['Failed to fetch steps', stepError])
})

test('day edit uses empty intake fallback and sends checked updates', async () => {
  responses = [{
    day: {
      id: '1',
      planId: 'p7',
      day: '2026-01-11',
      dayNum: 3,
      deficit: 600,
      tracked: false,
      completed: false,
      energyKcalGoal: 200.5,
      energyKcal: 190.4,
      proteinGGoal: 150,
      proteinG: 123.5,
      fatGGoal: 50,
      fatG: 49.5,
      carbsGGoal: 250.1,
      carbsG: 250.7,
      tdee: 2100,
    },
  }, { updateDay: { id: '1' } }]
  render(React.createElement(EditDayPage))
  await waitForEditLoaded()
  const checkbox = screen.getByRole('checkbox', { name: 'Tracked' })
  assert.equal(checkbox.checked, false)
  fireEvent.click(checkbox)
  await waitFor(() => assert.equal(checkbox.checked, true))
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests[1].variables.id, '42'))
  assert.equal(requests[1].variables.tracked, true)
  assert.equal(screen.getByText('No intakes logged for this day.').textContent, 'No intakes logged for this day.')
})

test('plan edit covers completed-yes and null day list fallback', async () => {
  responses = [{
    weekPlan: {
      id: 'p42',
      startDate: '2026-01-05',
      proteinGKg: 2,
      fatPerc: 22,
      deficit: 300,
      twee: 1530,
      completed: true,
      energyKcalGoal: 2100.2,
      energyKcal: 2022.9,
      days: null,
    },
  }, { updateWeekPlan: { id: 'p42' } }]
  render(React.createElement(EditPlanPage))
  await waitForEditLoaded()
  fireEvent.change(screen.getByLabelText('Deficit (kcals)'), { target: { value: '320' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests[1].variables.id, '42'))
  assert.equal(screen.queryAllByTestId(/^row-/).length, 0)

  assert.equal(requests[1].variables.proteinGKg, 2)
  assert.equal(requests[1].variables.fatPerc, 22)
  assert.equal(requests[1].variables.deficit, 320)
})

test('new exercise sends provided duration and distance values', async () => {
  const pending = deferred()
  responses = [() => pending.promise]
  render(React.createElement(NewExercisePage))
  fireEvent.change(screen.getByLabelText('Day ID'), { target: { value: '11' } })
  fireEvent.change(screen.getByLabelText('Kcals'), { target: { value: '520' } })
  fireEvent.change(screen.getByLabelText('Time'), { target: { value: '06:15' } })
  fireEvent.change(screen.getByLabelText('Duration (hh:mm:ss)'), { target: { value: '01:30:00' } })
  fireEvent.change(screen.getByLabelText('Distance (km)'), { target: { value: '3.75' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'true'))
  assert.deepEqual(requests[0].variables, {
    dayId: 11,
    type: 'walk',
    kcals: 520,
    time: '06:15',
    duration: '01:30:00',
    distance: 3.75,
  })
  pending.resolve({ createExercise: { id: 'e3' } })
  await waitFor(() => assert.equal(document.querySelector('form').dataset.saving, 'false'))
})

test('edit exercise loads nullable duration, keeps distance, and submits converted values', async () => {
  responses = [{
    exercise: {
      id: 'e100',
      dayId: 8,
      time: '10:20:30',
      type: 'run',
      kcals: 280,
      duration: null,
      distance: 3.5,
    },
  }, { updateExercise: { id: 'e100' } }]
  render(React.createElement(EditExercisePage))
  await waitForEditLoaded()
  assert.equal(screen.getByLabelText('Duration (hh:mm:ss)').value, '')
  assert.equal(screen.getByLabelText('Distance (km)').value, '3.5')
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests[1].variables.id, '42'))
  assert.deepEqual(requests[1].variables, {
    id: '42',
    type: 'run',
    kcals: 280,
    time: '10:20',
    duration: null,
    distance: 3.5,
  })
})

test('edit intake applies custom-form zero defaults and executes delete', async () => {
  responses = [{
    intake: {
      id: 'i3',
      dayId: '9',
      foodId: null,
      meal: 'breakfast',
      numServings: 2,
      energyKcal: 500,
      proteinG: 40,
      fatG: 20,
      carbsG: 30,
    },
  }, { updateIntake: { id: 'i3' } }]
  render(React.createElement(EditIntakePage))
  await waitForEditLoaded()
  fireEvent.change(screen.getByLabelText('Energy (kcal)'), { target: { value: '' } })
  fireEvent.change(screen.getByLabelText('Protein (g)'), { target: { value: '' } })
  fireEvent.change(screen.getByLabelText('Fat (g)'), { target: { value: '' } })
  fireEvent.change(screen.getByLabelText('Carbs (g)'), { target: { value: '' } })
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => assert.equal(requests[1].variables.id, '42'))
  assert.deepEqual(requests[1].variables, {
    id: '42',
    meal: 'breakfast',
    numServings: 2,
    energyKcal: 0,
    proteinG: 0,
    fatG: 0,
    carbsG: 0,
  })
  cleanup()
  requests.length = 0
  responses = [{ deleteIntake: { id: 'i3' } }]
  responses.unshift({
    intake: {
      id: 'i3',
      dayId: '9',
      foodId: 'f2',
      meal: 'breakfast',
      numServings: 2,
      energyKcal: 500,
      proteinG: 40,
      fatG: 20,
      carbsG: 30,
    },
  })
  render(React.createElement(EditIntakePage))
  await waitForEditLoaded()
  fireEvent.click(screen.getByText('Delete'))
  await waitFor(() => assert.equal(requests[1].variables.id, '42'))
  assert.deepEqual(requests[1].variables, { id: '42' })
})

test('steps list logs delete failures', async () => {
  const deleteError = new Error('steps delete failed')
  responses = [{ dayStepsList: [{ id: 's1', dayId: 2, steps: 1234, kcals: 43.1 }] }]
  render(React.createElement(StepsPage))
  await waitForTableLoaded()
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(globalThis, 'confirm').mockImplementation(() => true)
  responses = [deleteError]
  fireEvent.click(screen.getByText('delete-s1'))
  await waitFor(() => assert.deepEqual(consoleError.mock.calls[0], ['Failed to delete steps', deleteError]))
})
