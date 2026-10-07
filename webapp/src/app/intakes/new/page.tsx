'use client'

import { localDateInputValue } from '@/lib/dateInput'
import { useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/components/EntityForm'
import { FormField, ReadonlyField, SelectField } from '@/components/FormField'
import { buildCustomIntakeVariables } from './intakeVariables'

const CREATE_MUTATION = gql`
  mutation CreateIntake(
    $dayId: Int, $dayDate: String, $meal: String!, $numServings: Float!, $foodId: ID,
    $energyKcal: Float, $proteinG: Float, $fatG: Float, $carbsG: Float
  ) {
    createIntake(
      dayId: $dayId, dayDate: $dayDate, meal: $meal, numServings: $numServings, foodId: $foodId,
      energyKcal: $energyKcal, proteinG: $proteinG, fatG: $fatG, carbsG: $carbsG
    ) { id }
  }
`

const CONTEXT_QUERY = gql`
  query IntakeContext(
    $productId: ID!, $servingId: ID!,
    $requestedDayId: ID,
    $includeProduct: Boolean!, $includeServing: Boolean!
  ) {
    intakeDays(requestedId: $requestedDayId) { id day }
    foodProduct(id: $productId) @include(if: $includeProduct) {
      id name brand size sizeUnit
      servings { id servingSize servingUnit }
    }
    intakeFood(id: $servingId) @include(if: $includeServing) {
      servingId foodId name brand servingSize servingUnit
    }
  }
`

const MEAL_CHOICES = [
  { value: 'breakfast', label: 'Breakfast' },
  { value: 'lunch', label: 'Lunch' },
  { value: 'snack', label: 'Snack' },
  { value: 'dinner', label: 'Dinner' },
]

interface IntakeProduct {
  id: string
  name: string
  brand: string | null
  size: number
  sizeUnit: string
  servings: Array<{
    id: string
    servingSize: number
    servingUnit: string
  }>
}

interface IntakeFood {
  servingId: string
  foodId: string
  name: string
  brand: string | null
  servingSize: number
  servingUnit: string
}

interface DayOption {
  id: string
  day: string
}

interface IntakeContextResponse {
  intakeDays?: DayOption[]
  // Compatibility for isolated test fixtures; production requests intakeDays.
  weekPlans?: Array<{ days: DayOption[] }>
  foodProduct?: IntakeProduct | null
  intakeFood?: IntakeFood | null
}

function NewIntakeForm({
  dayIdFromQuery,
  dayDateFromQuery,
  productId,
  servingId,
  mealFromQuery,
  numServingsFromQuery,
}: {
  dayIdFromQuery: string | null
  dayDateFromQuery: string | null
  productId: string | null
  servingId: string | null
  mealFromQuery: string | null
  numServingsFromQuery: string | null
}) {
  const conflictingContext = Boolean(productId && servingId)
  const [form, setForm] = useState(() => ({
    dayId: '', dayDate: dayDateFromQuery ?? localDateInputValue(),
    meal: mealFromQuery ?? 'breakfast', numServings: numServingsFromQuery ?? '1.0',
    servingId: '', energyKcal: '', proteinG: '', fatG: '', carbsG: ''
  }))
  const [saving, setSaving] = useState(false)
  const [product, setProduct] = useState<IntakeProduct | null>(null)
  const [intakeFood, setIntakeFood] = useState<IntakeFood | null>(null)
  const [contextLoading, setContextLoading] = useState(!conflictingContext)
  const [contextError, setContextError] = useState<string | null>(
    conflictingContext ? 'Choose either a product or a serving, not both.' : null,
  )

  useEffect(() => {
    if (conflictingContext) return
    let cancelled = false
    const fetchContext = async () => {
      try {
        const result = await graphqlRequest<IntakeContextResponse>(CONTEXT_QUERY, {
          productId: productId ?? '0',
          servingId: servingId ?? '0',
          requestedDayId: dayIdFromQuery,
          includeProduct: Boolean(productId),
          includeServing: Boolean(servingId),
        })
        if (cancelled) return
        const uniqueDays = Array.from(
          new Map(
            (result.intakeDays ?? (result.weekPlans ?? []).flatMap((plan) => plan.days))
              .map((day) => [day.id, day]),
          ).values(),
        ).sort((left, right) => right.day.localeCompare(left.day))
        const requestedDay = uniqueDays.find((day) => day.id === dayIdFromQuery)
        const defaultServing = result.foodProduct?.servings.find(
          (candidate) => candidate.servingUnit === 'serving',
        ) ?? result.foodProduct?.servings.find(
          (candidate) => candidate.servingUnit === 'container',
        ) ?? result.foodProduct?.servings[0]

        setProduct(result.foodProduct ?? null)
        setIntakeFood(result.intakeFood ?? null)
        setForm((current) => ({
          ...current,
          dayId: requestedDay?.id ?? '',
          dayDate: requestedDay?.day ?? current.dayDate,
          servingId: defaultServing?.id ?? '',
        }))
        if (dayIdFromQuery && !requestedDay) {
          setContextError('The selected day is not available.')
        } else if (productId && (!result.foodProduct || !defaultServing)) {
          setContextError('Unable to load the scanned product.')
        } else if (servingId && !result.intakeFood) {
          setContextError('Unable to load the selected food.')
        } else {
          setContextError(null)
        }
      } catch (error) {
        console.error('Failed to fetch intake context', error)
        if (!cancelled) {
          setContextError(
            productId
              ? 'Unable to load the scanned product.'
              : servingId
                ? 'Unable to load the selected food.'
                : 'Unable to load the intake form.',
          )
        }
      } finally {
        if (!cancelled) setContextLoading(false)
      }
    }
    void fetchContext()
    return () => { cancelled = true }
  }, [conflictingContext, dayIdFromQuery, productId, servingId])

  const handleChange = (name: string, value: string) => {
    setForm((current) => ({ ...current, [name]: value, ...(name === 'dayDate' ? { dayId: '' } : {}) }))
  }

  const parsedDate = new Date(`${form.dayDate}T00:00:00Z`)
  const validMeal = MEAL_CHOICES.some((choice) => choice.value === form.meal)
  const numServings = Number(form.numServings)
  const validNumServings = /^\d*\.?\d+(?:e[+-]?\d+)?$/i.test(form.numServings)
    && Number.isFinite(numServings) && numServings >= 0.1
  const validDate = /^\d{4}-\d{2}-\d{2}$/.test(form.dayDate)
    && !form.dayDate.startsWith('0000')
    && Number.isFinite(parsedDate.getTime())
    && parsedDate.toISOString().slice(0, 10) === form.dayDate

  const handleSave = async () => {
    if (!validDate) throw new Error('Enter a valid date.')
    if (!validMeal) throw new Error('Select a valid meal.')
    if (!validNumServings) throw new Error('Enter a valid number of servings (at least 0.1).')
    if (conflictingContext) {
      throw new Error('Choose either a product or a serving, not both')
    }
    setSaving(true)
    try {
      const selectedServingId = intakeFood?.servingId ?? form.servingId
      if (productId || servingId) {
        if (!selectedServingId) {
          throw new Error(
            productId
              ? 'The scanned product is not available'
              : 'The selected food is not available',
          )
        }
        await graphqlRequest(CREATE_MUTATION, {
          ...(form.dayId ? { dayId: parseInt(form.dayId, 10) } : { dayDate: form.dayDate }),
          foodId: selectedServingId,
          meal: form.meal,
          numServings,
        })
      } else {
        await graphqlRequest(CREATE_MUTATION, buildCustomIntakeVariables(form))
      }
    } finally { setSaving(false) }
  }

  const selectedFoodName = intakeFood
    ? `${intakeFood.brand ? `${intakeFood.brand} ` : ''}${intakeFood.name}`
    : null

  return (
    <EntityForm
      title={productId || servingId ? 'New Food Intake' : 'New Custom Intake'}
      backHref={form.dayId ? `/days/${encodeURIComponent(form.dayId)}` : '/intakes'}
      onSave={handleSave}
      saving={saving}
      disabled={contextLoading || Boolean(contextError) || !validDate || !validMeal || !validNumServings}
      fieldsets={[{
        title: 'Intake Details',
        content: (
          <>
            <div className="form-group">
              <label className="form-label" htmlFor="dayDate">Date</label>
              <input
                className="form-input" id="dayDate" name="dayDate" type="date"
                value={validDate ? form.dayDate : ''} required disabled={contextLoading}
                aria-invalid={!validDate} aria-describedby="intake-date-help"
                onChange={(event) => handleChange('dayDate', event.target.value)}
              />
              <p id="intake-date-help" className="text-sm text-slate-500">
                Missing weeks and days are created when you save. Set up an initial plan first.
              </p>
              {!validDate && <p role="alert" className="text-red-600">Enter a valid date.</p>}
            </div>
            <SelectField label="Meal" name="meal" value={validMeal ? form.meal : ''} onChange={handleChange} options={MEAL_CHOICES} required />
            {!validMeal && <p role="alert" className="text-red-600">Select a valid meal.</p>}
            <FormField label="Number of Servings" name="numServings" type="number" step="0.1" min="0.1" value={form.numServings} onChange={handleChange} required />
            {!validNumServings && <p role="alert" className="text-red-600">Enter a valid number of servings (at least 0.1).</p>}
            {contextLoading && <p role="status">Loading intake details...</p>}
            {contextError && <p role="alert" className="text-red-600">{contextError}</p>}
            {product && (
              <>
                <ReadonlyField
                  label="Food"
                  value={`${product.brand ? `${product.brand} ` : ''}${product.name} (${product.size} ${product.sizeUnit})`}
                />
                <SelectField
                  label="Serving"
                  name="servingId"
                  value={form.servingId}
                  onChange={handleChange}
                  options={product.servings.map((candidate) => ({
                    value: candidate.id,
                    label: `${candidate.servingSize} ${candidate.servingUnit}`,
                  }))}
                  required
                />
              </>
            )}
            {intakeFood && (
              <>
                <ReadonlyField label="Food" value={selectedFoodName} />
                <ReadonlyField
                  label="Serving"
                  value={`${intakeFood.servingSize} ${intakeFood.servingUnit}`}
                />
              </>
            )}
            {!productId && !servingId && !contextLoading && !contextError && (
              <>
                <p className="text-sm text-slate-400 mt-4 mb-2">Custom Macros (total intake)</p>
                <FormField label="Energy (kcal)" name="energyKcal" type="number" step="0.01" min="0" value={form.energyKcal} onChange={handleChange} />
                <FormField label="Protein (g)" name="proteinG" type="number" step="0.01" min="0" value={form.proteinG} onChange={handleChange} />
                <FormField label="Fat (g)" name="fatG" type="number" step="0.01" min="0" value={form.fatG} onChange={handleChange} />
                <FormField label="Carbs (g)" name="carbsG" type="number" step="0.01" min="0" value={form.carbsG} onChange={handleChange} />
              </>
            )}
          </>
        ),
      }]}
    />
  )
}

export default function NewIntakePage() {
  const searchParams = useSearchParams()
  const dayIdFromQuery = searchParams.get('dayId')?.trim() || null
  const dayDateFromQuery = searchParams.get('dayDate')
  const productId = searchParams.get('productId')?.trim() || null
  const servingId = searchParams.get('servingId')?.trim() || null
  const mealFromQuery = searchParams.get('intakeMeal')
  const numServingsFromQuery = searchParams.get('intakeNumServings')
  return (
    <NewIntakeForm
      key={JSON.stringify([dayIdFromQuery, dayDateFromQuery, productId, servingId, mealFromQuery, numServingsFromQuery])}
      dayIdFromQuery={dayIdFromQuery}
      dayDateFromQuery={dayDateFromQuery}
      productId={productId}
      servingId={servingId}
      mealFromQuery={mealFromQuery}
      numServingsFromQuery={numServingsFromQuery}
    />
  )
}
