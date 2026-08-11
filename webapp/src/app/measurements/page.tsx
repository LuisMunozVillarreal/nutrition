'use client'

import { useEffect, useMemo, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import DataTable, { Column } from '@/components/DataTable'
import { subscribeToPromise } from '@/lib/promiseSubscription'
import {
  buildWeightTrendSeries,
  millisecondsUntilNextLocalDay,
} from '@/components/dashboardHelpers'
import WeightTrendChart from '@/components/WeightTrendChart'

const MEASUREMENTS_QUERY = gql`
  query {
    measurements {
      id
      bodyFatPerc
      weight
      bmr
      createdAt
    }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteMeasurement($id: ID!) {
    deleteMeasurement(id: $id)
  }
`

interface Measurement {
  id: string
  bodyFatPerc: number | null
  weight: number
  bmr: number | null
  createdAt: string
}

type RangeSelection = 'lastMonth' | 'lastQuarter' | 'lastYear' | 'custom'
type PresetRangeSelection = Exclude<RangeSelection, 'custom'>

interface DateRange {
  startDate: string
  endDate: string
}

const PRESETS: { label: string; value: RangeSelection }[] = [
  { label: 'Last month', value: 'lastMonth' },
  { label: 'Last quarter', value: 'lastQuarter' },
  { label: 'Last year', value: 'lastYear' },
  { label: 'Custom', value: 'custom' },
]

const PRESET_DAY_SPANS: Record<PresetRangeSelection, number> = {
  lastMonth: 30,
  lastQuarter: 90,
  lastYear: 365,
}

const RANGE_LABELS: Record<RangeSelection, string> = {
  lastMonth: 'Last month',
  lastQuarter: 'Last quarter',
  lastYear: 'Last year',
  custom: 'Custom',
}

function formatInputDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

function computeRangePreset(value: PresetRangeSelection, now: Date): DateRange {
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const start = new Date(end)
  start.setDate(end.getDate() - (PRESET_DAY_SPANS[value] - 1))

  return { startDate: formatInputDate(start), endDate: formatInputDate(end) }
}

function validateCustomRange(startDate: string, endDate: string): string | null {
  if (!startDate || !endDate) return 'Pick both a start and end date to use a custom range.'
  if (startDate > endDate) return 'Start date must be on or before end date.'

  return null
}

const columns: Column<Measurement>[] = [
  { key: 'id', label: 'ID', accessor: (r) => r.id },
  {
    key: 'createdAt',
    label: 'Date',
    accessor: (r) => new Date(r.createdAt).toLocaleDateString(),
  },
  { key: 'bodyFatPerc', label: 'Body Fat (%)', accessor: (r) => r.bodyFatPerc ?? '—' },
  { key: 'weight', label: 'Weight (kg)', accessor: (r) => r.weight },
  {
    key: 'bmr',
    label: 'BMR',
    accessor: (r) => r.bmr === null ? '—' : Math.round(r.bmr),
  },
]

export default function MeasurementsPage() {
  const [data, setData] = useState<Measurement[]>([])
  const [loading, setLoading] = useState(true)
  const [rangeSelection, setRangeSelection] = useState<RangeSelection>('lastMonth')
  const [today, setToday] = useState(() => new Date())
  const [customStartDate, setCustomStartDate] = useState(formatInputDate(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29)))
  const [customEndDate, setCustomEndDate] = useState(formatInputDate(today))

  const loadData = () => graphqlRequest<{ measurements: Measurement[] }>(MEASUREMENTS_QUERY)
  const applyData = (res: { measurements: Measurement[] }) => setData(res.measurements)
  const reportLoadError = (err: unknown) => console.error('Failed to fetch measurements', err)
  const finishLoading = () => setLoading(false)

  const reloadData = () => {
    setLoading(true)
    return loadData().then(applyData, reportLoadError).then(finishLoading)
  }

  useEffect(() => subscribeToPromise(loadData(), {
    onFulfilled: applyData,
    onRejected: reportLoadError,
    onSettled: finishLoading,
  }), [])

  useEffect(() => {
    const timer = setTimeout(
      () => setToday(new Date()),
      millisecondsUntilNextLocalDay(today),
    )

    return () => clearTimeout(timer)
  }, [today])

  const handleDelete = async (row: Measurement) => {
    if (!confirm('Delete this measurement?')) return
    try {
      await graphqlRequest(DELETE_MUTATION, { id: row.id })
      await reloadData()
    } catch (err) {
      console.error('Failed to delete measurement', err)
    }
  }

  const selectedRange = useMemo(() => {
    if (rangeSelection === 'custom') {
      const error = validateCustomRange(customStartDate, customEndDate)

      if (error) return { startDate: '', endDate: '', error }

      return {
        startDate: customStartDate,
        endDate: customEndDate,
        error: null,
      }
    }

    return { ...computeRangePreset(rangeSelection, today), error: null }
  }, [rangeSelection, today, customStartDate, customEndDate])

  const series = useMemo(() => {
    if (selectedRange.error) return []

    return buildWeightTrendSeries(data, undefined, {
      startDate: selectedRange.startDate,
      endDate: selectedRange.endDate,
    })
  }, [data, selectedRange])

  const validRangeMessage = rangeSelection === 'custom' && selectedRange.error
    ? selectedRange.error
    : null

  const rangeLabel = rangeSelection === 'custom'
    ? `${customStartDate} to ${customEndDate}`
    : RANGE_LABELS[rangeSelection]

  return (
    <div>
      <h1 className="page-title mb-6" data-testid="measurements-title">Measurements</h1>
      <section className="glass-card mb-6 rounded-3xl p-6" aria-labelledby="weight-range-title">
        <div className="mb-4">
          <h2 id="weight-range-title" className="text-xl font-bold">Weight trend</h2>
          <p className="text-sm text-slate-400">Showing measurements for: {rangeLabel}</p>
        </div>
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label htmlFor="trend-range" className="flex w-full flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-widest text-slate-300">Trend range</span>
            <select
              id="trend-range"
              aria-label="Trend range"
              value={rangeSelection}
              onChange={(event) => setRangeSelection(event.target.value as RangeSelection)}
              className="rounded-xl border border-white/20 bg-slate-900/50 px-3 py-2"
            >
              {PRESETS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label htmlFor="trend-start-date" className="flex w-full flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-widest text-slate-300">Start date</span>
            <input
              id="trend-start-date"
              type="date"
              value={customStartDate}
              onChange={(event) => setCustomStartDate(event.target.value)}
              aria-invalid={Boolean(validRangeMessage)}
              aria-describedby={validRangeMessage ? 'trend-range-error' : undefined}
              disabled={rangeSelection !== 'custom'}
              className="rounded-xl border border-white/20 bg-slate-900/50 px-3 py-2"
            />
          </label>
          <label htmlFor="trend-end-date" className="flex w-full flex-col gap-1">
            <span className="text-xs font-semibold uppercase tracking-widest text-slate-300">End date</span>
            <input
              id="trend-end-date"
              type="date"
              value={customEndDate}
              onChange={(event) => setCustomEndDate(event.target.value)}
              aria-invalid={Boolean(validRangeMessage)}
              aria-describedby={validRangeMessage ? 'trend-range-error' : undefined}
              disabled={rangeSelection !== 'custom'}
              className="rounded-xl border border-white/20 bg-slate-900/50 px-3 py-2"
            />
          </label>
        </div>
        {validRangeMessage && (
          <p id="trend-range-error" role="alert" className="mb-2 text-sm text-red-300" aria-live="polite">
            {validRangeMessage}
          </p>
        )}
        {loading ? (
          <div className="h-44 rounded-2xl bg-white/5 animate-pulse" />
        ) : selectedRange.error ? null : (
          <WeightTrendChart
            series={series}
            emptyMessage={series.length === 0
              ? 'No measurements found for this date range.'
              : 'Log at least two measurements to see your trend'}
            emptyActionHref="/measurements/new"
            emptyActionLabel="Log weight"
          />
        )}
      </section>
      <DataTable
        columns={columns}
        data={data}
        loading={loading}
        rowHref={(r) => `/measurements/${r.id}`}
        addHref="/measurements/new"
        addLabel="New Measurement"
        onDelete={handleDelete}
        emptyMessage="No measurements yet. Add your first one!"
      />
    </div>
  )
}
