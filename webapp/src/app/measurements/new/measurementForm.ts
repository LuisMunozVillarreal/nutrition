export interface MeasurementFormState {
  bodyFatPerc: string
  weight: string
}

export function prefillPreviousBodyFat(
  form: MeasurementFormState,
  previousBodyFat: number | null,
  bodyFatTouched = false,
): MeasurementFormState {
  if (bodyFatTouched || form.bodyFatPerc !== '' || previousBodyFat === null) {
    return form
  }

  return { ...form, bodyFatPerc: String(previousBodyFat) }
}
