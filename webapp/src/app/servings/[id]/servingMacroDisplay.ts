export interface ServingMacroValues {
  energyKcal?: number | null
  proteinG?: number | null
  fatG?: number | null
  carbsG?: number | null
}

export type ServingMacroDisplayValue = number | '—'

function roundedDisplayValue(value: number | null | undefined): ServingMacroDisplayValue {
  return value === null || value === undefined ? '—' : Math.round(value)
}

export function servingMacroDisplayValues(values: ServingMacroValues) {
  return {
    energyKcal: roundedDisplayValue(values.energyKcal),
    proteinG: roundedDisplayValue(values.proteinG),
    fatG: roundedDisplayValue(values.fatG),
    carbsG: roundedDisplayValue(values.carbsG),
  }
}
