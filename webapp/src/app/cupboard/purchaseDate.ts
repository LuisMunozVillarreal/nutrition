export { localDateInputValue } from '../../lib/dateInput.ts'

export type PurchaseDateMonthStyle = 'short' | 'long'

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
