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

  const plot = buildTrendCoordinates(series, { width: 720, height: 180, padding: 20 })
  const first = series[0]
  const last = series.at(-1)!
  const change = last.weight - first.weight
  const label = `Weight trend from ${first.weight} kilograms to ${last.weight} kilograms, ${describeWeightTrendChange(change)}`

  return (
    <div>
      <svg role="img" aria-label={label} viewBox={plot.viewBox} className="h-44 w-full" preserveAspectRatio="none">
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
        {plot.points.map((point) => (
          <circle key={point.id} cx={point.x} cy={point.y} r="5" fill="rgb(216 180 254)">
            <title>{`${point.date}: ${point.weight} kg`}</title>
          </circle>
        ))}
      </svg>
      <div className="flex justify-between text-xs text-slate-400">
        <span>{first.date}</span><span>{last.date}</span>
      </div>
    </div>
  )
}

function EmptyValue({ message, href, linkText }: { message: string; href: string; linkText: string }) {
  return <div className="py-3"><p className="mb-2 text-slate-400">{message}</p><a href={href} className="text-sm font-bold text-purple-300 hover:text-purple-200">{linkText} →</a></div>
}
