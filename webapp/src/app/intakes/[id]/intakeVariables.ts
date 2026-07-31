export interface IntakeNutrientTotals {
  meal: string
  numServings: number
  energyKcal: number
  proteinG: number
  fatG: number
  carbsG: number
}

export interface CustomIntakeEditForm {
  meal: string
  numServings: string
  energyKcal: string
  proteinG: string
  fatG: string
  carbsG: string
}

export interface CustomIntakeUpdateVariables extends Record<string, unknown> {
  id: string
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

export function buildCustomIntakeEditForm(
  intake: IntakeNutrientTotals,
): CustomIntakeEditForm {
  return {
    meal: intake.meal,
    numServings: String(intake.numServings),
    energyKcal: String(intake.energyKcal),
    proteinG: String(intake.proteinG),
    fatG: String(intake.fatG),
    carbsG: String(intake.carbsG),
  }
}

export function buildCustomIntakeUpdateVariables(
  id: string,
  form: CustomIntakeEditForm,
): CustomIntakeUpdateVariables {
  const numServings = Number.parseFloat(form.numServings)

  return {
    id,
    meal: form.meal,
    numServings,
    energyKcal: destinationTotal(form.energyKcal),
    proteinG: destinationTotal(form.proteinG),
    fatG: destinationTotal(form.fatG),
    carbsG: destinationTotal(form.carbsG),
  }
}
