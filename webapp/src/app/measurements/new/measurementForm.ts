export interface MeasurementFormState {
  bodyFatPerc: string
  weight: string
}

export function prefillPreviousBodyFat(
  form: MeasurementFormState,
  previousBodyFat: number | null,
): MeasurementFormState {
  if (form.bodyFatPerc !== '' || previousBodyFat === null) return form

  return { ...form, bodyFatPerc: String(previousBodyFat) }
}
