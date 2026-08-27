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

const PRODUCT_QUERY = gql`
  query IntakeProduct($foodId: ID!) {
    foodProduct(id: $foodId) { id name brand size sizeUnit }
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
}

export default function NewIntakePage() {
  const searchParams = useSearchParams()
  const dayIdFromQuery = searchParams.get('dayId')
  const foodId = searchParams.get('foodId')?.trim() || null
  const [form, setForm] = useState(() => ({
    dayId: dayIdFromQuery ?? '', meal: 'breakfast', numServings: '1.0',
    energyKcal: '', proteinG: '', fatG: '', carbsG: ''
  }))
  const [saving, setSaving] = useState(false)
  const [product, setProduct] = useState<IntakeProduct | null>(null)
  const [productLoading, setProductLoading] = useState(Boolean(foodId))
  const [productError, setProductError] = useState<string | null>(null)

  useEffect(() => {
    if (!foodId) return
    let cancelled = false
    const fetchProduct = async () => {
      try {
        const result = await graphqlRequest<{ foodProduct: IntakeProduct | null }>(
          PRODUCT_QUERY,
          { foodId },
        )
        if (cancelled) return
        if (result.foodProduct) {
          setProductError(null)
          setProduct(result.foodProduct)
        } else {
          setProductError('Unable to load the scanned product.')
        }
      } catch (error) {
        console.error('Failed to fetch intake product', error)
        if (!cancelled) setProductError('Unable to load the scanned product.')
      } finally {
        if (!cancelled) setProductLoading(false)
      }
    }
    void fetchProduct()
    return () => { cancelled = true }
  }, [foodId])

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      if (foodId) {
        if (!product) throw new Error('The scanned product is not available')
        await graphqlRequest(CREATE_MUTATION, {
          dayId: parseInt(form.dayId, 10),
          foodId,
          meal: form.meal,
          numServings: parseFloat(form.numServings),
        })
      } else {
        await graphqlRequest(CREATE_MUTATION, buildCustomIntakeVariables(form))
      }
    } finally { setSaving(false) }
  }

  return (
    <EntityForm
      title={foodId ? 'New Product Intake' : 'New Custom Intake'}
      backHref={dayIdFromQuery ? `/days/${encodeURIComponent(dayIdFromQuery)}` : '/days'}
      onSave={handleSave}
      saving={saving}
      disabled={Boolean(foodId) && (productLoading || Boolean(productError))}
      fieldsets={[{
        title: 'Intake Details',
        content: (
          <>
            <FormField label="Day ID" name="dayId" type="number" value={form.dayId} onChange={handleChange} required />
            <SelectField label="Meal" name="meal" value={form.meal} onChange={handleChange} options={MEAL_CHOICES} required />
            <FormField label="Number of Servings" name="numServings" type="number" step="0.1" min="0.1" value={form.numServings} onChange={handleChange} required />
            {foodId ? (
              <>
                {productLoading && <p role="status">Loading product...</p>}
                {productError && <p role="alert" className="text-red-600">{productError}</p>}
                {product && (
                  <ReadonlyField
                    label="Product"
                    value={`${product.brand ? `${product.brand} ` : ''}${product.name} (${product.size} ${product.sizeUnit})`}
                  />
                )}
              </>
            ) : (
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
