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
        {plot.points.map((point) => (
          <span
            key={point.id}
            data-testid="weight-trend-dot"
            role="img"
            tabIndex={0}
            aria-label={`Measurement on ${point.date}: ${point.weight} kilograms`}
            title={`${point.date}: ${point.weight} kg`}
            className="absolute size-2.5 -translate-x-1/2 -translate-y-1/2 cursor-help rounded-full bg-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-100"
            style={{
              left: `${(point.x / chartWidth) * 100}%`,
              top: `${(point.y / chartHeight) * 100}%`,
            }}
          />
        ))}
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
