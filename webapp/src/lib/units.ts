export interface UnitChoice {
  value: string
  label: string
}

const MASS_UNITS = new Set(['mg', 'g', 'kg', 'oz', 'lb'])
const VOLUME_UNITS = new Set(['ml', 'cl', 'l', 'c', 'floz', 'tbsp', 'tsp', 'pt'])
const CONTEXTUAL_UNITS = new Set(['unit', 'serving', 'container'])

export const UNIT_CHOICES: UnitChoice[] = [
  { value: 'mg', label: 'mg' },
  { value: 'g', label: 'g' },
  { value: 'kg', label: 'kg' },
  { value: 'oz', label: 'oz' },
  { value: 'lb', label: 'lb' },
  { value: 'ml', label: 'ml' },
  { value: 'cl', label: 'cl' },
  { value: 'l', label: 'l' },
  { value: 'c', label: 'cup' },
  { value: 'floz', label: 'fl oz' },
  { value: 'tbsp', label: 'tbsp' },
  { value: 'tsp', label: 'tsp' },
  { value: 'pt', label: 'pint' },
  { value: 'unit', label: 'unit' },
  { value: 'container', label: 'container' },
  { value: 'serving', label: 'serving' },
]

export function isCompatibleUnitPair(first: string, second: string): boolean {
  if (first === second) return true
  return (
    (MASS_UNITS.has(first) && MASS_UNITS.has(second)) ||
    (VOLUME_UNITS.has(first) && VOLUME_UNITS.has(second))
  )
}

export function compatibleUnits(reference: string): UnitChoice[] {
  return UNIT_CHOICES.filter(({ value }) => isCompatibleUnitPair(value, reference))
}

export function servingUnitChoices(
  sizeUnit: string,
  nutritionalInfoUnit: string,
): UnitChoice[] {
  return UNIT_CHOICES.filter(({ value }) => {
    if (value === 'container' || value === 'serving') {
      return isCompatibleUnitPair(sizeUnit, nutritionalInfoUnit)
    }
    if (CONTEXTUAL_UNITS.has(value) && value !== sizeUnit) return false
    return (
      isCompatibleUnitPair(value, sizeUnit) &&
      isCompatibleUnitPair(value, nutritionalInfoUnit)
    )
  })
}
