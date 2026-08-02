export interface MeasurementFormState {
  bodyFatPerc: string
  weight: string
}

interface PreviousBodyFatLookupOptions {
  lookup: () => Promise<number | null>
  updateForm: (
    update: (form: MeasurementFormState) => MeasurementFormState,
  ) => void
  isTouched: () => boolean
  isCancelled: () => boolean
  onError: (error: unknown) => void
}

export async function loadAndPrefillPreviousBodyFat({
  lookup,
  updateForm,
  isTouched,
  isCancelled,
  onError,
}: PreviousBodyFatLookupOptions): Promise<void> {
  try {
    const previousBodyFat = await lookup()
    if (isCancelled()) return

    updateForm((form) => prefillPreviousBodyFat(
      form,
      previousBodyFat,
      isTouched(),
    ))
  } catch (error) {
    if (!isCancelled()) onError(error)
  }
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
