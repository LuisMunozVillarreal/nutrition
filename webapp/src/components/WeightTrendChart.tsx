import { useId } from 'react'

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

export default function WeightTrendChart({
  series,
  emptyMessage,
  emptyActionHref,
  emptyActionLabel,
}: WeightTrendChartProps) {
  const chartId = useId()

  if (series.length < 2) {
    return (
      <EmptyValue
        message={emptyMessage}
        href={emptyActionHref}
        linkText={emptyActionLabel}
      />
    )
  }

  const plot = buildTrendCoordinates(series, { width: 720, height: 180, padding: 20 })
  const first = series[0]
  const last = series.at(-1)!
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
          const tooltipPosition = index === 0
            ? 'left-0'
            : index === plot.points.length - 1
              ? 'right-0'
              : 'left-1/2 -translate-x-1/2'

          return (
            <span
              key={point.id}
              role="img"
              tabIndex={0}
              aria-label={pointLabel}
              aria-describedby={descriptionId}
              onPointerDown={(event) => event.currentTarget.focus()}
              className="group absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-purple-300 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-100 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900"
              style={{
                left: `${(point.x / 720) * 100}%`,
                top: `${(point.y / 180) * 100}%`,
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
    </div>
  )
}

function EmptyValue({ message, href, linkText }: { message: string; href: string; linkText: string }) {
  return <div className="py-3"><p className="mb-2 text-slate-400">{message}</p><a href={href} className="text-sm font-bold text-purple-300 hover:text-purple-200">{linkText} →</a></div>
}
