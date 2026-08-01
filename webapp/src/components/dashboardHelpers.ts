export interface DashboardMeasurement {
  id: string
  createdAt: string
  weight: number
  bodyFatPerc: number
}

export interface WeightTrendPoint {
  id: string
  date: string
  weight: number
}

export function millisecondsUntilNextLocalDay(now = new Date()): number {
  const nextDay = new Date(now)
  nextDay.setHours(24, 0, 0, 0)
  return Math.max(1, nextDay.getTime() - now.getTime())
}

export function describeWeightTrendChange(change: number): string {
  if (change === 0) return 'unchanged'
  const direction = change > 0 ? 'up' : 'down'
  return `${direction} ${Math.abs(change).toFixed(1)} kilograms`
}

export function normalizeDateForComparison(
  value: string,
  timezoneOffsetMinutes?: number,
): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return value.slice(0, 10)
  const offset = timezoneOffsetMinutes ?? date.getTimezoneOffset()
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 10)
}

export function isCurrentLocalDate(value: string, now = new Date()): boolean {
  return value === normalizeDateForComparison(now.toISOString(), now.getTimezoneOffset())
}

export function buildWeightTrendSeries(
  measurements: DashboardMeasurement[],
  limit = 14,
): WeightTrendPoint[] {
  return [...measurements]
    .filter((measurement) => Number.isFinite(measurement.weight))
    .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
    .slice(-limit)
    .map((measurement) => ({
      id: measurement.id,
      date: normalizeDateForComparison(measurement.createdAt),
      weight: measurement.weight,
    }))
}

export function buildTrendCoordinates(
  series: WeightTrendPoint[],
  dimensions: { width: number; height: number; padding: number },
) {
  const { width, height, padding } = dimensions
  const weights = series.map((point) => point.weight)
  const min = Math.min(...weights)
  const max = Math.max(...weights)
  const range = max - min
  const availableWidth = width - padding * 2
  const availableHeight = height - padding * 2

  const points = series.map((point, index) => ({
    ...point,
    x:
      series.length === 1
        ? width / 2
        : padding + (index / (series.length - 1)) * availableWidth,
    y:
      range === 0
        ? height / 2
        : padding + ((max - point.weight) / range) * availableHeight,
  }))
  const path = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ')

  return { points, path, viewBox: `0 0 ${width} ${height}` }
}
