import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  buildTrendCoordinates,
  buildWeightTrendSeries,
  describeWeightTrendChange,
  isCurrentLocalDate,
  millisecondsUntilNextLocalDay,
  normalizeDateForComparison,
} from '../src/components/dashboardHelpers.ts'

test('trend helpers sort weights by date and trim to recent points', () => {
  const measurements = [
    { id: '1', createdAt: '2026-02-01T10:00:00Z', weight: 80, bodyFatPerc: 21 },
    { id: '2', createdAt: '2026-02-03T10:00:00Z', weight: 79.2, bodyFatPerc: 20.6 },
    { id: '3', createdAt: '2026-01-30T10:00:00Z', weight: 81, bodyFatPerc: 21.3 },
    { id: '4', createdAt: '2026-02-02T10:00:00Z', weight: 79.8, bodyFatPerc: 20.9 },
  ]

  const trend = buildWeightTrendSeries(measurements, 3)

  assert.deepEqual(trend.map((entry) => entry.weight), [80, 79.8, 79.2])
  assert.deepEqual(
    trend.map((entry) => entry.date),
    ['2026-02-01', '2026-02-02', '2026-02-03'],
  )
})

test('trend coordinate mapping is bounded and stable for flat series', () => {
  const trendPoints = buildWeightTrendSeries([
    { id: '1', createdAt: '2026-02-01T00:00:00Z', weight: 70, bodyFatPerc: 21 },
    { id: '2', createdAt: '2026-02-02T00:00:00Z', weight: 70, bodyFatPerc: 20.5 },
    { id: '3', createdAt: '2026-02-03T00:00:00Z', weight: 70, bodyFatPerc: 20 },
  ], 3)

  const plot = buildTrendCoordinates(trendPoints, {
    width: 320,
    height: 120,
    padding: 20,
  })

  assert.equal(plot.points.length, 3)
  assert.equal(plot.points[0].x, 20)
  assert.equal(plot.points[2].x, 300)
  assert.equal(plot.points[0].y, plot.points[2].y)
  assert.equal(plot.path.startsWith('M 20 '), true)
  assert.equal(typeof plot.viewBox, 'string')
})

test('measurement dates use the local calendar date across midnight offsets', () => {
  assert.equal(
    normalizeDateForComparison('2026-02-03T00:30:00Z', 120),
    '2026-02-02',
  )
  assert.equal(
    normalizeDateForComparison('2026-02-03T23:30:00Z', -120),
    '2026-02-04',
  )
  assert.equal(normalizeDateForComparison('2026-02-03'), '2026-02-03')
})

test('dashboard refresh helpers handle midnight rollover and flat trends', () => {
  const thirtySecondsBeforeMidnight = new Date(2026, 1, 3, 23, 59, 30)

  assert.equal(millisecondsUntilNextLocalDay(thirtySecondsBeforeMidnight), 30_000)
  assert.equal(describeWeightTrendChange(0), 'unchanged')
  assert.equal(describeWeightTrendChange(0.4), 'up 0.4 kilograms')
  assert.equal(describeWeightTrendChange(-0.4), 'down 0.4 kilograms')
  assert.equal(
    isCurrentLocalDate('2026-02-03', new Date(2026, 1, 3, 23, 59, 30)),
    true,
  )
  assert.equal(
    isCurrentLocalDate('2026-02-02', new Date(2026, 1, 3, 0, 0, 1)),
    false,
  )
})

test('dashboard query and actions include required data shape and remove hydration placeholder', async () => {
  const dashboardSource = await readFile(
    new URL('../src/components/Dashboard.tsx', import.meta.url),
    'utf8',
  )

  assert.match(dashboardSource, /DASHBOARD_QUERY/)
  assert.match(dashboardSource, /latestWeight/)
  assert.match(dashboardSource, /latestBodyFat/)
  assert.match(dashboardSource, /goalBodyFat/)
  assert.match(dashboardSource, /dashboard\(timezoneOffsetMinutes:/)
  assert.match(dashboardSource, /recentMeasurements\s*\{/)
  assert.match(dashboardSource, /todayNutrition\s*\{/)
  assert.match(dashboardSource, /intakeCount/)
  assert.doesNotMatch(dashboardSource, /^\s*measurements\s*\{/m)
  assert.doesNotMatch(dashboardSource, /weekPlans\s*\{/)
  assert.match(dashboardSource, /Log today weight/i)
  assert.match(dashboardSource, /Log a meal/i)
  assert.match(dashboardSource, /role="progressbar"/)
  assert.match(dashboardSource, /aria-valuetext=/)
  assert.match(dashboardSource, /key=\{point\.id\}/)
  assert.match(dashboardSource, /flex justify-between text-xs text-slate-400/)
  assert.match(dashboardSource, /millisecondsUntilNextLocalDay/)
  assert.match(dashboardSource, /visibilitychange/)
  assert.match(dashboardSource, /requestSequence/)
  assert.match(dashboardSource, /isCurrentLocalDate\(today\.day\)/)
  assert.match(dashboardSource, /!loading && todayIsCurrent/)
  assert.match(dashboardSource, /today && todayIsCurrent \?/)
  assert.match(dashboardSource, /uppercase tracking-wider text-slate-400/)
  assert.doesNotMatch(dashboardSource, /Hydration/)
  assert.doesNotMatch(dashboardSource, /Measurement logging.*unavailable/i)
})

test('intake form source reads dayId from query parameters', async () => {
  const intakeSource = await readFile(
    new URL('../src/app/intakes/new/page.tsx', import.meta.url),
    'utf8',
  )

  assert.match(intakeSource, /useSearchParams/)
  assert.match(intakeSource, /dayIdFromQuery = searchParams\.get\('dayId'\)/)
  assert.match(intakeSource, /const \[form, setForm\] = useState\(\(\) => \(\{[^}]*dayId:/s)

  const { buildCustomIntakeVariables } = await import(
    '../src/app/intakes/new/intakeVariables.ts'
  )
  assert.equal(buildCustomIntakeVariables({
    dayId: '42',
    meal: 'breakfast',
    numServings: '1',
    energyKcal: '',
    proteinG: '',
    fatG: '',
    carbsG: '',
  }).dayId, 42)
})
