'use client'

import { useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/app/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/app/components/FormField'

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

const UNIT_CHOICES = [
  { value: 'g', label: 'g' },
  { value: 'ml', label: 'ml' },
  { value: 'fl oz', label: 'fl oz' },
  { value: 'oz', label: 'oz' },
  { value: 'container', label: 'container' },
  { value: 'serving', label: 'serving' },
]

export default function NewProductPage() {
  const [form, setForm] = useState({
    name: '', brand: '', barcode: '', notes: '',
    nutritionalInfoSize: '100', nutritionalInfoUnit: 'g',
    size: '100', sizeUnit: 'g', numServings: '1.0',
    energyKcal: '0', proteinG: '0', fatG: '0', carbsG: '0',
    saturatedFatG: '', sugarsG: '', fibreG: '', saltG: ''
  })
  const [saving, setSaving] = useState(false)

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(CREATE_MUTATION, {
        name: form.name,
        brand: form.brand || null,
        barcode: form.barcode || null,
        notes: form.notes,
        nutritionalInfoSize: parseFloat(form.nutritionalInfoSize),
        nutritionalInfoUnit: form.nutritionalInfoUnit,
        size: parseFloat(form.size),
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
                <FormField label="Size" name="size" type="number" step="0.1" value={form.size} onChange={handleChange} required />
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
              <SelectField label="Info Unit Base" name="nutritionalInfoUnit" value={form.nutritionalInfoUnit} onChange={handleChange} options={UNIT_CHOICES} required helpText="e.g. g" />
            </div>
          ),
        },
        {
          title: 'Main Nutrients (Per Info Base)',
          content: (
            <>
              <FormField label="Energy (kcal)" name="energyKcal" type="number" step="0.1" value={form.energyKcal} onChange={handleChange} required />
              <FormField label="Protein (g)" name="proteinG" type="number" step="0.1" value={form.proteinG} onChange={handleChange} required />
              <FormField label="Fat (g)" name="fatG" type="number" step="0.1" value={form.fatG} onChange={handleChange} required />
              <FormField label="Carbs (g)" name="carbsG" type="number" step="0.1" value={form.carbsG} onChange={handleChange} required />
            </>
          ),
        },
        {
          title: 'Extra Nutrients (Per Info Base)',
          content: (
            <>
              <FormField label="Saturated Fat (g)" name="saturatedFatG" type="number" step="0.1" value={form.saturatedFatG} onChange={handleChange} />
              <FormField label="Sugars (g)" name="sugarsG" type="number" step="0.1" value={form.sugarsG} onChange={handleChange} />
              <FormField label="Fibre (g)" name="fibreG" type="number" step="0.1" value={form.fibreG} onChange={handleChange} />
              <FormField label="Salt (g)" name="saltG" type="number" step="0.1" value={form.saltG} onChange={handleChange} />
            </>
          ),
        },
      ]}
    />
  )
}
