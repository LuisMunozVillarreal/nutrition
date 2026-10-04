export interface CustomIntakeForm {
  dayId: string
  dayDate?: string
  meal: string
  numServings: string
  energyKcal: string
  proteinG: string
  fatG: string
  carbsG: string
}

export interface CustomIntakeVariables extends Record<string, unknown> {
  dayId?: number
  dayDate?: string
  meal: string
  numServings: number
  energyKcal: number
  proteinG: number
  fatG: number
  carbsG: number
}

function destinationTotal(value: string): number {
  return value ? Number.parseFloat(value) : 0
}

export function buildCustomIntakeVariables(
  form: CustomIntakeForm,
): CustomIntakeVariables {
  const numServings = Number.parseFloat(form.numServings)

  return {
    ...(form.dayId ? { dayId: Number.parseInt(form.dayId, 10) } : { dayDate: form.dayDate }),
    meal: form.meal,
    numServings,
    energyKcal: destinationTotal(form.energyKcal),
    proteinG: destinationTotal(form.proteinG),
    fatG: destinationTotal(form.fatG),
    carbsG: destinationTotal(form.carbsG),
  }
}
