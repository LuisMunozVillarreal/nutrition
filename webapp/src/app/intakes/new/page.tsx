'use client'

import { useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/components/EntityForm'
import { FormField, ReadonlyField, SelectField } from '@/components/FormField'
import { buildCustomIntakeVariables } from './intakeVariables'

const CREATE_MUTATION = gql`
  mutation CreateIntake(
    $dayId: Int!, $meal: String!, $numServings: Float!, $foodId: ID,
    $energyKcal: Float, $proteinG: Float, $fatG: Float, $carbsG: Float
  ) {
    createIntake(
      dayId: $dayId, meal: $meal, numServings: $numServings, foodId: $foodId,
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

function localDateKey(): string {
  const date = new Date()
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-')
}

function dayLabel(value: string): string {
  const [year, month, day] = value.split('-').map(Number)
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)))
}

function NewIntakeForm({
  dayIdFromQuery,
  productId,
  servingId,
}: {
  dayIdFromQuery: string | null
  productId: string | null
  servingId: string | null
}) {
  const conflictingContext = Boolean(productId && servingId)
  const [form, setForm] = useState(() => ({
    dayId: '', meal: 'breakfast', numServings: '1.0',
    servingId: '', energyKcal: '', proteinG: '', fatG: '', carbsG: ''
  }))
  const [saving, setSaving] = useState(false)
  const [product, setProduct] = useState<IntakeProduct | null>(null)
  const [intakeFood, setIntakeFood] = useState<IntakeFood | null>(null)
  const [days, setDays] = useState<DayOption[]>([])
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
        const today = uniqueDays.find((day) => day.day === localDateKey())
        const selectedDay = dayIdFromQuery
          ? requestedDay
          : today ?? uniqueDays[0]
        const defaultServing = result.foodProduct?.servings.find(
          (candidate) => candidate.servingUnit === 'serving',
        ) ?? result.foodProduct?.servings.find(
          (candidate) => candidate.servingUnit === 'container',
        ) ?? result.foodProduct?.servings[0]

        setDays(uniqueDays)
        setProduct(result.foodProduct ?? null)
        setIntakeFood(result.intakeFood ?? null)
        setForm((current) => ({
          ...current,
          dayId: selectedDay?.id ?? '',
          servingId: defaultServing?.id ?? '',
        }))
        if (dayIdFromQuery && !requestedDay) {
          setContextError('The selected day is not available.')
        } else if (productId && (!result.foodProduct || !defaultServing)) {
          setContextError('Unable to load the scanned product.')
        } else if (servingId && !result.intakeFood) {
          setContextError('Unable to load the selected food.')
        } else if (!selectedDay) {
          setContextError('No plan days are available for logging this intake.')
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
    setForm((current) => ({ ...current, [name]: value }))
  }

  const handleSave = async () => {
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
          dayId: parseInt(form.dayId, 10),
          foodId: selectedServingId,
          meal: form.meal,
          numServings: parseFloat(form.numServings),
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
      backHref={form.dayId ? `/days/${encodeURIComponent(form.dayId)}` : '/days'}
      onSave={handleSave}
      saving={saving}
      disabled={contextLoading || Boolean(contextError) || !form.dayId}
      fieldsets={[{
        title: 'Intake Details',
        content: (
          <>
            <SelectField
              label="Day"
              name="dayId"
              value={form.dayId}
              onChange={handleChange}
              options={days.map((day) => ({ value: day.id, label: dayLabel(day.day) }))}
              required
            />
            <SelectField label="Meal" name="meal" value={form.meal} onChange={handleChange} options={MEAL_CHOICES} required />
            <FormField label="Number of Servings" name="numServings" type="number" step="0.1" min="0.1" value={form.numServings} onChange={handleChange} required />
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
  const productId = searchParams.get('productId')?.trim() || null
  const servingId = searchParams.get('servingId')?.trim() || null
  return (
    <NewIntakeForm
      key={JSON.stringify([dayIdFromQuery, productId, servingId])}
      dayIdFromQuery={dayIdFromQuery}
      productId={productId}
      servingId={servingId}
    />
  )
}
