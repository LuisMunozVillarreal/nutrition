import { useEffect, useState } from 'react'

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

interface ActiveSelection {
  pointId: string
  series: WeightTrendPoint[]
}

export default function WeightTrendChart({
  series,
  emptyMessage,
  emptyActionHref,
  emptyActionLabel,
}: WeightTrendChartProps) {
  const [pointerSelection, setPointerSelection] = useState<ActiveSelection | null>(null)
  const [focusSelection, setFocusSelection] = useState<ActiveSelection | null>(null)
  const activeSelection = pointerSelection?.series === series
    ? pointerSelection
    : focusSelection?.series === series
      ? focusSelection
      : null
  const activePointId = activeSelection?.pointId ?? null

  useEffect(() => {
    if (activePointId === null) return

    const dismissOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setPointerSelection(null)
        setFocusSelection(null)
      }
    }

    window.addEventListener('keydown', dismissOnEscape)
    return () => window.removeEventListener('keydown', dismissOnEscape)
  }, [activePointId])

  if (series.length < 2) {
    return (
      <EmptyValue
        message={emptyMessage}
        href={emptyActionHref}
        linkText={emptyActionLabel}
      />
    )
  }

  const chartWidth = 720
  const chartHeight = 180
  const plot = buildTrendCoordinates(series, { width: chartWidth, height: chartHeight, padding: 20 })
  const activePoint = plot.points.find((point) => point.id === activePointId)
  const tooltipId = 'weight-trend-tooltip'
  const first = series[0]
  const last = series.at(-1)!
  const change = last.weight - first.weight
  const label = `Weight trend from ${first.weight} kilograms to ${last.weight} kilograms, ${describeWeightTrendChange(change)}`

  return (
    <div
      data-testid="weight-trend-interaction"
      onMouseLeave={() => setPointerSelection(null)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocusSelection(null)
      }}
    >
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
            data-testid="weight-trend-dot"
            role="img"
            tabIndex={0}
            aria-label={`Measurement on ${point.date}: ${point.weight} kilograms`}
            aria-describedby={activePoint?.id === point.id ? tooltipId : undefined}
            className="absolute size-2.5 -translate-x-1/2 -translate-y-1/2 cursor-help rounded-full bg-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-100"
            style={{
              left: `${(point.x / chartWidth) * 100}%`,
              top: `${(point.y / chartHeight) * 100}%`,
            }}
            onMouseEnter={() => setPointerSelection({ pointId: point.id, series })}
            onFocus={() => {
              setPointerSelection(null)
              setFocusSelection({ pointId: point.id, series })
            }}
          />
        ))}
      </div>
      <div className="min-h-7 w-full py-1 text-center">
        {activePoint && (
          <span
            id={tooltipId}
            role="tooltip"
            className="block w-full max-w-full rounded-md bg-slate-950 px-2 py-1 text-xs font-medium text-white shadow-lg"
          >
            {activePoint.date}: {activePoint.weight} kg
          </span>
        )}
      </div>
      <div className="flex justify-between text-xs text-slate-400">
        <span>{first.date}</span><span>{last.date}</span>
      </div>
    </div>
  )
}

function EmptyValue({ message, href, linkText }: { message: string; href: string; linkText: string }) {
  return <div className="py-3"><p className="mb-2 text-slate-400">{message}</p><a href={href} className="text-sm font-bold text-purple-300 hover:text-purple-200">{linkText} →</a></div>
}
