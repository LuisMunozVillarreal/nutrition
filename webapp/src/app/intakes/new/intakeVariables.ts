export interface CustomIntakeForm {
  dayId: string
  meal: string
  numServings: string
  energyKcal: string
  proteinG: string
  fatG: string
  carbsG: string
}

export interface CustomIntakeVariables extends Record<string, unknown> {
  dayId: number
  meal: string
  numServings: number
  energyKcal: number
  proteinG: number
  fatG: number
  carbsG: number
}

function macroTotal(value: string, numServings: number): number {
  return value ? Number.parseFloat(value) * numServings : 0
}

export function buildCustomIntakeVariables(
  form: CustomIntakeForm,
): CustomIntakeVariables {
  const numServings = Number.parseFloat(form.numServings)

  return {
    dayId: Number.parseInt(form.dayId, 10),
    meal: form.meal,
    numServings,
    energyKcal: macroTotal(form.energyKcal, numServings),
    proteinG: macroTotal(form.proteinG, numServings),
    fatG: macroTotal(form.fatG, numServings),
    carbsG: macroTotal(form.carbsG, numServings),
  }
}
