import { useState } from 'react'

import {
  buildTrendCoordinates,
  describeWeightTrendChange,
  type WeightTrendPoint,
} from './dashboardHelpers'

interface WeightTrendChartProps {
  series: WeightTrendPoint[]
  emptyMessage: string
  emptyActionHref: string
  emptyActionLabel: string
}

const CHART_WIDTH = 720
const CHART_HEIGHT = 180
const CHART_PADDING = 20

export default function WeightTrendChart(props: WeightTrendChartProps) {
  const seriesKey = JSON.stringify(
    props.series.map((point) => [point.id, point.date, point.timestamp, point.weight]),
  )

  return <WeightTrendChartContent key={seriesKey} {...props} />
}

function WeightTrendChartContent({
  series,
  emptyMessage,
  emptyActionHref,
  emptyActionLabel,
}: WeightTrendChartProps) {
  const [activePointIndex, setActivePointIndex] = useState(0)

  if (series.length < 2) {
    return (
      <EmptyValue
        message={emptyMessage}
        href={emptyActionHref}
        linkText={emptyActionLabel}
      />
    )
  }

  const plot = buildTrendCoordinates(series, {
    width: CHART_WIDTH,
    height: CHART_HEIGHT,
    padding: CHART_PADDING,
  })
  const first = series[0]
  const last = series.at(-1)!
  const selectedPointIndex = activePointIndex
  const selectedPoint = plot.points[selectedPointIndex]
  const selectedPointLabel = describeTrendPoint(
    selectedPoint,
    selectedPointIndex,
    plot.points.length,
  )
  const change = last.weight - first.weight
  const label = `Weight trend from ${first.weight} kilograms to ${last.weight} kilograms, ${describeWeightTrendChange(change)}`

  return (
    <div>
      <div className="relative h-44 w-full">
        <svg role="img" aria-label={label} viewBox={plot.viewBox} className="absolute inset-0 h-full w-full" preserveAspectRatio="none">
          <title>{label}</title>
          <path
            d={plot.path}
            fill="none"
            stroke="rgb(192 132 252)"
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        {plot.points.map((point) => (
          <span
            key={point.id}
            data-testid="weight-trend-marker"
            aria-hidden="true"
            className="pointer-events-none absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-purple-300 shadow-sm"
            style={{
              left: `${(point.x / CHART_WIDTH) * 100}%`,
              top: `${(point.y / CHART_HEIGHT) * 100}%`,
            }}
          />
        ))}
      </div>
      <div className="flex justify-between text-xs text-slate-400">
        <span>{first.date}</span><span>{last.date}</span>
      </div>
      <label className="mt-2 block text-xs text-slate-300">
        <span className="sr-only">Inspect weight trend point</span>
        <input
          type="range"
          min="0"
          max={plot.points.length - 1}
          step="1"
          value={selectedPointIndex}
          aria-label="Inspect weight trend point"
          aria-valuetext={selectedPointLabel}
          onChange={(event) => setActivePointIndex(Number(event.target.value))}
          className="h-11 w-full cursor-pointer accent-purple-300"
        />
        <output data-testid="weight-trend-selected-point" className="block text-center">
          {selectedPointLabel}
        </output>
      </label>
    </div>
  )
}

function describeTrendPoint(point: WeightTrendPoint, index: number, total: number): string {
  return `Point ${index + 1} of ${total}, ${point.date}: ${point.weight} kg`
}

function EmptyValue({ message, href, linkText }: { message: string; href: string; linkText: string }) {
  return <div className="py-3"><p className="mb-2 text-slate-400">{message}</p><a href={href} className="text-sm font-bold text-purple-300 hover:text-purple-200">{linkText} →</a></div>
}
