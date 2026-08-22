import { useId, useState } from 'react'

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

export default function WeightTrendChart({
  series,
  emptyMessage,
  emptyActionHref,
  emptyActionLabel,
}: WeightTrendChartProps) {
  const chartId = useId()
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
  const selectedPointIndex = Math.min(activePointIndex, plot.points.length - 1)
  const selectedPoint = plot.points[selectedPointIndex]
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
        {plot.points.map((point, index) => {
          const pointLabel = `${point.date}: ${point.weight} kg`
          const descriptionId = `${chartId}-point-${index}`
          const tooltipPosition = point.x <= CHART_WIDTH * 0.1
            ? 'left-0'
            : point.x >= CHART_WIDTH * 0.9
              ? 'right-0'
              : 'left-1/2 -translate-x-1/2'

          return (
            <span
              key={point.id}
              role="img"
              tabIndex={0}
              aria-labelledby={descriptionId}
              onPointerDown={(event) => event.currentTarget.focus()}
              className="group absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-purple-300 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-100 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900"
              style={{
                left: `${(point.x / CHART_WIDTH) * 100}%`,
                top: `${(point.y / CHART_HEIGHT) * 100}%`,
              }}
            >
              <span
                id={descriptionId}
                className={`pointer-events-none absolute bottom-full z-10 mb-2 whitespace-nowrap rounded bg-slate-950 px-2 py-1 text-xs text-white opacity-0 shadow transition-opacity group-hover:opacity-100 group-focus:opacity-100 ${tooltipPosition}`}
              >
                {pointLabel}
              </span>
            </span>
          )
        })}
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
          aria-valuetext={`${selectedPoint.date}: ${selectedPoint.weight} kg`}
          onChange={(event) => setActivePointIndex(Number(event.target.value))}
          className="h-11 w-full cursor-pointer accent-purple-300"
        />
        <output role="status" aria-live="polite" className="block text-center">
          {selectedPoint.date}: {selectedPoint.weight} kg
        </output>
      </label>
    </div>
  )
}

function EmptyValue({ message, href, linkText }: { message: string; href: string; linkText: string }) {
  return <div className="py-3"><p className="mb-2 text-slate-400">{message}</p><a href={href} className="text-sm font-bold text-purple-300 hover:text-purple-200">{linkText} →</a></div>
}
