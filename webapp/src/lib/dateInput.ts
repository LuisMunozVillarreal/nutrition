export function localDateInputValue(
  date: Date = new Date(),
  timezoneOffsetMinutes: number = date.getTimezoneOffset(),
): string {
  const localTime = new Date(date.getTime() - timezoneOffsetMinutes * 60_000)
  return localTime.toISOString().slice(0, 10)
}
