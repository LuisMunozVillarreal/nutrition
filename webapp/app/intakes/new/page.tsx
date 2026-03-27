'use client'

import { useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/app/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/app/components/FormField'

const CREATE_MUTATION = gql`
  mutation CreateIntake(
    $dayId: Int!, $meal: String!, $numServings: Float!,
    $energyKcal: Float, $proteinG: Float, $fatG: Float, $carbsG: Float
  ) {
    createIntake(
      dayId: $dayId, meal: $meal, numServings: $numServings,
      energyKcal: $energyKcal, proteinG: $proteinG, fatG: $fatG, carbsG: $carbsG
    ) { id }
  }
`

const MEAL_CHOICES = [
  { value: 'breakfast', label: 'Breakfast' },
  { value: 'lunch', label: 'Lunch' },
  { value: 'snack', label: 'Snack' },
  { value: 'dinner', label: 'Dinner' },
]

export default function NewIntakePage() {
  const [form, setForm] = useState({
    dayId: '', meal: 'breakfast', numServings: '1.0',
    energyKcal: '', proteinG: '', fatG: '', carbsG: ''
  })
  const [saving, setSaving] = useState(false)

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(CREATE_MUTATION, {
        dayId: parseInt(form.dayId),
        meal: form.meal,
        numServings: parseFloat(form.numServings),
        energyKcal: form.energyKcal ? parseFloat(form.energyKcal) : 0,
        proteinG: form.proteinG ? parseFloat(form.proteinG) : 0,
        fatG: form.fatG ? parseFloat(form.fatG) : 0,
        carbsG: form.carbsG ? parseFloat(form.carbsG) : 0,
      })
    } finally { setSaving(false) }
  }

  return (
    <EntityForm
      title="New Custom Intake"
      backHref="/days"
      onSave={handleSave}
      saving={saving}
      fieldsets={[{
        title: 'Intake Details',
        content: (
          <>
            <FormField label="Day ID" name="dayId" type="number" value={form.dayId} onChange={handleChange} required />
            <SelectField label="Meal" name="meal" value={form.meal} onChange={handleChange} options={MEAL_CHOICES} required />
            <FormField label="Number of Servings" name="numServings" type="number" step="0.1" value={form.numServings} onChange={handleChange} required />
            <p className="text-sm text-slate-400 mt-4 mb-2">Custom Macros (per serving)</p>
            <FormField label="Energy (kcal)" name="energyKcal" type="number" step="0.1" value={form.energyKcal} onChange={handleChange} />
            <FormField label="Protein (g)" name="proteinG" type="number" step="0.1" value={form.proteinG} onChange={handleChange} />
            <FormField label="Fat (g)" name="fatG" type="number" step="0.1" value={form.fatG} onChange={handleChange} />
            <FormField label="Carbs (g)" name="carbsG" type="number" step="0.1" value={form.carbsG} onChange={handleChange} />
          </>
        ),
      }]}
    />
  )
}
