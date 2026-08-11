import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'vitest'

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
    { id: '1', createdAt: '2026-02-01', weight: 80, bodyFatPerc: 21 },
    { id: '2', createdAt: '2026-02-03', weight: 79.2, bodyFatPerc: 20.6 },
    { id: '3', createdAt: '2026-01-30', weight: 81, bodyFatPerc: 21.3 },
    { id: '4', createdAt: '2026-02-02', weight: 79.8, bodyFatPerc: 20.9 },
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

test('trend coordinate mapping spaces measurements by elapsed time', () => {
  const trendPoints = buildWeightTrendSeries([
    { id: '1', createdAt: '2026-02-01T00:00:00Z', weight: 70, bodyFatPerc: 21 },
    { id: '2', createdAt: '2026-02-02T00:00:00Z', weight: 69.8, bodyFatPerc: 20.5 },
    { id: '3', createdAt: '2026-02-09T00:00:00Z', weight: 69.5, bodyFatPerc: 20 },
  ], 3)

  const plot = buildTrendCoordinates(trendPoints, {
    width: 100,
    height: 80,
    padding: 10,
  })

  assert.deepEqual(plot.points.map((point) => point.x), [10, 20, 90])
})

test('trend coordinate mapping reflects elapsed time even within the same day', () => {
  const trendPoints = buildWeightTrendSeries([
    { id: '1', createdAt: '2026-02-01T08:00:00Z', weight: 70, bodyFatPerc: 21 },
    { id: '2', createdAt: '2026-02-01T20:00:00Z', weight: 69.8, bodyFatPerc: 20.5 },
  ])

  const plot = buildTrendCoordinates(trendPoints, {
    width: 100,
    height: 80,
    padding: 10,
  })

  assert.deepEqual(plot.points.map((point) => point.x), [10, 90])
})

test('trend helpers filter inclusive ranges without timezone assumptions or default truncation', () => {
  const measurements = Array.from({ length: 20 }, (_, index) => ({
    id: String(index + 1),
    createdAt: `2026-02-${String(index + 1).padStart(2, '0')}`,
    weight: 70 - index / 10,
    bodyFatPerc: 21 - index / 20,
  }))

  const points = buildWeightTrendSeries(
    measurements,
    undefined,
    { startDate: '2026-02-01', endDate: '2026-02-20' },
  )

  assert.equal(points.length, 20)
  assert.equal(points[0].id, '1')
  assert.equal(points.at(-1).id, '20')
  assert.equal(points[0].date, '2026-02-01')
  assert.equal(points.at(-1).date, '2026-02-20')
})

test('trend helpers discard malformed timestamps before building finite SVG geometry', () => {
  const points = buildWeightTrendSeries([
    { id: '1', createdAt: '2026-02-01', weight: 70.2, bodyFatPerc: 21 },
    { id: 'bad-date', createdAt: '2026-02-02-not-a-time', weight: 70.1, bodyFatPerc: 20.5 },
    { id: '3', createdAt: '2026-02-03', weight: 70, bodyFatPerc: 20.4 },
  ], undefined, { startDate: '2026-02-01', endDate: '2026-02-03' })

  assert.deepEqual(points.map((point) => point.id), ['1', '3'])
  const plot = buildTrendCoordinates(points, { width: 100, height: 80, padding: 10 })
  assert.equal(plot.points.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y)), true)
  assert.doesNotMatch(plot.path, /NaN|Infinity/)
})

test('trend series filters non-finite weights and handles a single point', () => {
  const measurements = [
    { id: 'bad', createdAt: '2026-02-01T00:00:00Z', weight: Number.NaN, bodyFatPerc: 21 },
    { id: 'inf', createdAt: '2026-02-01T01:00:00Z', weight: Number.POSITIVE_INFINITY, bodyFatPerc: 21 },
    { id: 'ok', createdAt: '2026-02-02T00:00:00Z', weight: 70.5, bodyFatPerc: 20.5 },
  ]

  const filtered = buildWeightTrendSeries(measurements)
  assert.deepEqual(filtered.map((entry) => entry.weight), [70.5])

  const single = buildWeightTrendSeries([measurements[2]])
  const plot = buildTrendCoordinates(single, { width: 320, height: 120, padding: 20 })
  assert.equal(plot.points.length, 1)
  assert.equal(plot.points[0].x, 160)
  assert.equal(plot.points[0].y, 60)
  assert.equal(plot.path, 'M 160 60')
})

test('date helpers tolerate values that are not parseable dates', () => {
  assert.equal(normalizeDateForComparison('not-a-date'), 'not-a-date')
  assert.equal(normalizeDateForComparison('2026-02-03'), '2026-02-03')
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
  const trendChartSource = await readFile(
    new URL('../src/components/WeightTrendChart.tsx', import.meta.url),
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
  assert.match(trendChartSource, /key=\{point\.id\}/)
  assert.match(trendChartSource, /flex justify-between text-xs text-slate-400/)
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
