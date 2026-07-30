export type PurchaseDateMonthStyle = 'short' | 'long'

export function localDateInputValue(
  date: Date = new Date(),
  timezoneOffsetMinutes: number = date.getTimezoneOffset(),
): string {
  const localTime = new Date(date.getTime() - timezoneOffsetMinutes * 60_000)
  return localTime.toISOString().slice(0, 10)
}

export function purchaseDateToISOString(date: string): string {
  return `${date}T00:00:00.000Z`
}

export function formatPurchaseDate(
  purchasedAt: string,
  month: PurchaseDateMonthStyle,
): string {
  return new Intl.DateTimeFormat('en-US', {
    month,
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(purchasedAt))
}
