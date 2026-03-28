'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/components/FormField'

const INTAKE_QUERY = gql`
  query GetIntake($id: ID!) {
    intake(id: $id) {
      id dayId foodId numServings meal mealOrder
      energyKcal proteinG fatG carbsG
    }
  }
`

const UPDATE_MUTATION = gql`
  mutation UpdateIntake(
    $id: ID!, $meal: String!, $numServings: Float!,
    $energyKcal: Float, $proteinG: Float, $fatG: Float, $carbsG: Float
  ) {
    updateIntake(
      id: $id, meal: $meal, numServings: $numServings,
      energyKcal: $energyKcal, proteinG: $proteinG, fatG: $fatG, carbsG: $carbsG
    ) { id }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteIntake($id: ID!) {
    deleteIntake(id: $id)
  }
`

const MEAL_CHOICES = [
  { value: 'breakfast', label: 'Breakfast' },
  { value: 'lunch', label: 'Lunch' },
  { value: 'snack', label: 'Snack' },
  { value: 'dinner', label: 'Dinner' },
]

export default function EditIntakePage() {
  const params = useParams()
  const id = params.id as string
  const [form, setForm] = useState({
    meal: 'breakfast', numServings: '1.0',
    energyKcal: '', proteinG: '', fatG: '', carbsG: ''
  })
  const [readOnly, setReadOnly] = useState<any>({})
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{ intake: any }>(INTAKE_QUERY, { id })
        if (res.intake) {
          setForm({
            meal: res.intake.meal,
            numServings: String(res.intake.numServings),
            energyKcal: String(res.intake.energyKcal),
            proteinG: String(res.intake.proteinG),
            fatG: String(res.intake.fatG),
            carbsG: String(res.intake.carbsG),
          })
          setReadOnly({ dayId: res.intake.dayId, foodId: res.intake.foodId })
        }
      } catch (err) { console.error('Failed to fetch intake', err) }
      setLoading(false)
    }
    fetchData()
  }, [id])

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(UPDATE_MUTATION, {
        id, meal: form.meal, numServings: parseFloat(form.numServings),
        energyKcal: form.energyKcal ? parseFloat(form.energyKcal) : 0,
        proteinG: form.proteinG ? parseFloat(form.proteinG) : 0,
        fatG: form.fatG ? parseFloat(form.fatG) : 0,
        carbsG: form.carbsG ? parseFloat(form.carbsG) : 0,
      })
    } finally { setSaving(false) }
  }

  const handleDelete = async () => { await graphqlRequest(DELETE_MUTATION, { id }) }

  if (loading) return <div className="p-12 text-center text-slate-500">Loading...</div>

  // If tied to a food, we don't allow modifying macros
  const isCustom = !readOnly.foodId

  return (
    <EntityForm
      title="Edit Intake"
      backHref={`/days/${readOnly.dayId}`}
      onSave={handleSave}
      onDelete={handleDelete}
      saving={saving}
      fieldsets={[{
        title: 'Intake Details',
        content: (
          <>
            <SelectField label="Meal" name="meal" value={form.meal} onChange={handleChange} options={MEAL_CHOICES} required />
            <FormField label="Number of Servings" name="numServings" type="number" step="0.1" value={form.numServings} onChange={handleChange} required />
            
            <div className="mt-6 mb-2">
              <p className="text-sm font-semibold text-slate-300">Macros</p>
              {!isCustom && <p className="text-xs text-slate-500">Computed from Food Product (read-only)</p>}
            </div>

            {isCustom ? (
              <>
                <FormField label="Energy (kcal)" name="energyKcal" type="number" step="0.1" value={form.energyKcal} onChange={handleChange} />
                <FormField label="Protein (g)" name="proteinG" type="number" step="0.1" value={form.proteinG} onChange={handleChange} />
                <FormField label="Fat (g)" name="fatG" type="number" step="0.1" value={form.fatG} onChange={handleChange} />
                <FormField label="Carbs (g)" name="carbsG" type="number" step="0.1" value={form.carbsG} onChange={handleChange} />
              </>
            ) : (
              <>
                <ReadonlyField label="Energy (kcal)" value={form.energyKcal} />
                <ReadonlyField label="Protein (g)" value={form.proteinG} />
                <ReadonlyField label="Fat (g)" value={form.fatG} />
                <ReadonlyField label="Carbs (g)" value={form.carbsG} />
              </>
            )}
          </>
        ),
      }]}
    />
  )
}
