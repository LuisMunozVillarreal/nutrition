export function optionalNumberInput(
  value: number | null | undefined,
): string {
  return value == null ? '' : String(value)
}

export function optionalNumberVariable(value: string): number | null {
  return value === '' ? null : Number.parseFloat(value)
}
