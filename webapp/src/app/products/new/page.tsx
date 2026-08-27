'use client'

import { Suspense, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/components/EntityForm'
import { FormField, SelectField, TextareaField } from '@/components/FormField'
import { compatibleUnits, isCompatibleUnitPair, UNIT_CHOICES } from '@/lib/units'

const CREATE_MUTATION = gql`
  mutation CreateFoodProduct(
    $name: String!, $brand: String, $barcode: String, $notes: String!,
    $nutritionalInfoSize: Float!, $nutritionalInfoUnit: String!,
    $size: Float!, $sizeUnit: String!, $numServings: Float!,
    $energyKcal: Float!, $proteinG: Float!, $fatG: Float!, $carbsG: Float!,
    $saturatedFatG: Float, $sugarsG: Float, $fibreG: Float, $saltG: Float
  ) {
    createFoodProduct(
      name: $name, brand: $brand, barcode: $barcode, notes: $notes,
      nutritionalInfoSize: $nutritionalInfoSize, nutritionalInfoUnit: $nutritionalInfoUnit,
      size: $size, sizeUnit: $sizeUnit, numServings: $numServings,
      energyKcal: $energyKcal, proteinG: $proteinG, fatG: $fatG, carbsG: $carbsG,
      saturatedFatG: $saturatedFatG, sugarsG: $sugarsG, fibreG: $fibreG, saltG: $saltG
    ) { id }
  }
`

interface ProductFormState {
  name: string
  brand: string
  barcode: string
  notes: string
  nutritionalInfoSize: string
  nutritionalInfoUnit: string
  size: string
  sizeUnit: string
  numServings: string
  energyKcal: string
  proteinG: string
  fatG: string
  carbsG: string
  saturatedFatG: string
  sugarsG: string
  fibreG: string
  saltG: string
}

const DEFAULT_FORM: ProductFormState = {
  name: '', brand: '', barcode: '', notes: '',
  nutritionalInfoSize: '100', nutritionalInfoUnit: 'g',
  size: '100', sizeUnit: 'g', numServings: '1.0',
  energyKcal: '', proteinG: '', fatG: '', carbsG: '',
  saturatedFatG: '', sugarsG: '', fibreG: '', saltG: ''
}

// Fields the scan page can prefill through the query string.
const PREFILL_FIELDS: Array<keyof ProductFormState> = [
  'barcode', 'brand', 'name', 'size', 'sizeUnit', 'numServings',
  'nutritionalInfoSize', 'nutritionalInfoUnit', 'energyKcal', 'proteinG',
  'fatG', 'carbsG', 'saturatedFatG', 'sugarsG', 'fibreG', 'saltG'
]

const REQUIRED_MAIN_NUTRIENTS: Array<keyof ProductFormState> = [
  'energyKcal',
  'proteinG',
  'fatG',
  'carbsG',
]

function initialForm(searchParams: URLSearchParams): ProductFormState {
  const form = { ...DEFAULT_FORM }
  if (
    searchParams.get('fromBarcodeScan') === '1' &&
    searchParams.get('size') === null
  ) {
    form.size = ''
  }
  for (const field of PREFILL_FIELDS) {
    const value = searchParams.get(field)
    if (value !== null) form[field] = value
  }
  return form
}

function NewProductForm() {
  const searchParams = useSearchParams()
  const intakeDayId = searchParams.get('fromBarcodeScan') === '1'
    ? searchParams.get('intakeDayId')?.trim() || null
    : null
  const [form, setForm] = useState(() => initialForm(searchParams))
  const [saving, setSaving] = useState(false)

  const handleChange = (name: string, value: string) => {
    setForm(prev => {
      if (name === 'sizeUnit' && !isCompatibleUnitPair(value, prev.nutritionalInfoUnit)) {
        return { ...prev, sizeUnit: value, nutritionalInfoUnit: value }
      }
      return { ...prev, [name]: value }
    })
  }

  const handleSave = async () => {
    const size = Number(form.size)
    if (!form.size.trim() || !Number.isFinite(size) || size <= 0) {
      throw new Error('Enter a valid package size before saving')
    }
    if (REQUIRED_MAIN_NUTRIENTS.some((field) => !form[field].trim())) {
      throw new Error('Enter all required main nutrients before saving')
    }
    setSaving(true)
    try {
      const result = await graphqlRequest<{ createFoodProduct: { id: string } }>(CREATE_MUTATION, {
        name: form.name,
        brand: form.brand || null,
        barcode: form.barcode || null,
        notes: form.notes,
        nutritionalInfoSize: parseFloat(form.nutritionalInfoSize),
        nutritionalInfoUnit: form.nutritionalInfoUnit,
        size,
        sizeUnit: form.sizeUnit,
        numServings: parseFloat(form.numServings),
        energyKcal: parseFloat(form.energyKcal),
        proteinG: parseFloat(form.proteinG),
        fatG: parseFloat(form.fatG),
        carbsG: parseFloat(form.carbsG),
        saturatedFatG: form.saturatedFatG ? parseFloat(form.saturatedFatG) : null,
        sugarsG: form.sugarsG ? parseFloat(form.sugarsG) : null,
        fibreG: form.fibreG ? parseFloat(form.fibreG) : null,
        saltG: form.saltG ? parseFloat(form.saltG) : null,
      })
      if (intakeDayId) {
        const params = new URLSearchParams({
          dayId: intakeDayId,
          foodId: result.createFoodProduct.id,
        })
        return `/intakes/new?${params.toString()}`
      }
    } finally { setSaving(false) }
  }

  return (
    <EntityForm
      title="New Food Product"
      backHref="/products"
      onSave={handleSave}
      saving={saving}
      fieldsets={[
        {
          title: 'General',
          content: (
            <>
              <FormField label="Brand" name="brand" value={form.brand} onChange={handleChange} />
              <FormField label="Name" name="name" value={form.name} onChange={handleChange} required />
              <FormField label="Barcode" name="barcode" value={form.barcode} onChange={handleChange} />
              <TextareaField label="Notes" name="notes" value={form.notes} onChange={handleChange} />

              <div className="grid grid-cols-2 gap-4 mt-4">
                <FormField label="Size" name="size" type="number" step="0.1" min="0.1" value={form.size} onChange={handleChange} required />
                <SelectField label="Size Unit" name="sizeUnit" value={form.sizeUnit} onChange={handleChange} options={UNIT_CHOICES} required />
              </div>
              <FormField label="Number of Servings (in size)" name="numServings" type="number" step="0.1" value={form.numServings} onChange={handleChange} required />
            </>
          ),
        },
        {
          title: 'Nutritional Info Base',
          content: (
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Info Size Base" name="nutritionalInfoSize" type="number" step="0.1" value={form.nutritionalInfoSize} onChange={handleChange} required helpText="e.g. 100" />
              <SelectField label="Info Unit Base" name="nutritionalInfoUnit" value={form.nutritionalInfoUnit} onChange={handleChange} options={compatibleUnits(form.sizeUnit)} required helpText="e.g. g" />
            </div>
          ),
        },
        {
          title: 'Main Nutrients (Per Info Base)',
          content: (
            <>
              <FormField label="Energy (kcal)" name="energyKcal" type="number" step="0.1" min="0" value={form.energyKcal} onChange={handleChange} required />
              <FormField label="Protein (g)" name="proteinG" type="number" step="0.1" min="0" value={form.proteinG} onChange={handleChange} required />
              <FormField label="Fat (g)" name="fatG" type="number" step="0.1" min="0" value={form.fatG} onChange={handleChange} required />
              <FormField label="Carbs (g)" name="carbsG" type="number" step="0.1" min="0" value={form.carbsG} onChange={handleChange} required />
            </>
          ),
        },
        {
          title: 'Extra Nutrients (Per Info Base)',
          content: (
            <>
              <FormField label="Saturated Fat (g)" name="saturatedFatG" type="number" step="0.1" min="0" value={form.saturatedFatG} onChange={handleChange} />
              <FormField label="Sugars (g)" name="sugarsG" type="number" step="0.1" min="0" value={form.sugarsG} onChange={handleChange} />
              <FormField label="Fibre (g)" name="fibreG" type="number" step="0.1" min="0" value={form.fibreG} onChange={handleChange} />
              <FormField label="Salt (g)" name="saltG" type="number" step="0.1" min="0" value={form.saltG} onChange={handleChange} />
            </>
          ),
        },
      ]}
    />
  )
}

export default function NewProductPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-slate-500">Loading form...</div>}>
      <NewProductForm />
    </Suspense>
  )
}
