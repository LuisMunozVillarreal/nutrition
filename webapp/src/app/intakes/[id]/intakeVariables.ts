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

function perServing(total: number, numServings: number): string {
  return String(total / numServings)
}

function macroTotal(value: string, numServings: number): number {
  return value ? Number.parseFloat(value) * numServings : 0
}

export function buildCustomIntakeEditForm(
  intake: IntakeNutrientTotals,
): CustomIntakeEditForm {
  return {
    meal: intake.meal,
    numServings: String(intake.numServings),
    energyKcal: perServing(intake.energyKcal, intake.numServings),
    proteinG: perServing(intake.proteinG, intake.numServings),
    fatG: perServing(intake.fatG, intake.numServings),
    carbsG: perServing(intake.carbsG, intake.numServings),
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
    energyKcal: macroTotal(form.energyKcal, numServings),
    proteinG: macroTotal(form.proteinG, numServings),
    fatG: macroTotal(form.fatG, numServings),
    carbsG: macroTotal(form.carbsG, numServings),
  }
}
