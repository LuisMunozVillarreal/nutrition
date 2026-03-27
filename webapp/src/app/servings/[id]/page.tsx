'use client'

import { useEffect, useState, Suspense } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import { graphqlRequest, gql } from '../../../lib/graphql'
import EntityForm from '../../../components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '../../../components/FormField'

const SERVING_QUERY = gql`
  query GetServing($id: ID!, $foodId: ID!) {
    foodProduct(id: $foodId) {
      servings {
        id servingSize servingUnit energyKcal proteinG fatG carbsG
      }
    }
  }
`

const UPDATE_MUTATION = gql`
  mutation UpdateServing($id: ID!, $servingSize: Float!, $servingUnit: String!) {
    updateServing(id: $id, servingSize: $servingSize, servingUnit: $servingUnit) { id }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteServing($id: ID!) {
    deleteServing(id: $id)
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

function EditServingForm() {
  const params = useParams()
  const id = params.id as string
  const searchParams = useSearchParams()
  const foodId = searchParams.get('foodId')
  
  const [form, setForm] = useState({ servingSize: '', servingUnit: '' })
  const [readOnly, setReadOnly] = useState<any>({})
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      if (!foodId) {
        setLoading(false)
        return
      }
      try {
        const res = await graphqlRequest<{ foodProduct: { servings: any[] } }>(SERVING_QUERY, { id, foodId })
        const serving = res.foodProduct?.servings?.find(s => s.id === id)
        if (serving) {
          setForm({
            servingSize: String(serving.servingSize),
            servingUnit: serving.servingUnit,
          })
          setReadOnly(serving)
        }
      } catch (err) { console.error('Failed to fetch serving', err) }
      setLoading(false)
    }
    fetchData()
  }, [id, foodId])

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(UPDATE_MUTATION, {
        id,
        servingSize: parseFloat(form.servingSize),
        servingUnit: form.servingUnit,
      })
    } finally { setSaving(false) }
  }

  const handleDelete = async () => { await graphqlRequest(DELETE_MUTATION, { id }) }

  if (loading) return <div className="p-12 text-center text-slate-500">Loading...</div>

  return (
    <EntityForm
      title="Edit Serving"
      backHref={foodId ? `/products/${foodId}` : "/products"}
      onSave={handleSave}
      onDelete={handleDelete}
      saving={saving}
      fieldsets={[
        {
          title: 'Serving Details',
          content: (
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Size" name="servingSize" type="number" step="0.1" value={form.servingSize} onChange={handleChange} required />
              <SelectField label="Unit" name="servingUnit" value={form.servingUnit} onChange={handleChange} options={UNIT_CHOICES} required />
            </div>
          ),
        },
        {
          title: 'Computed Macros (Read-only)',
          content: (
            <>
              <p className="text-xs text-slate-500 mb-4">Values below are derived from the Food Product base nutrition and current serving ratio.</p>
              <ReadonlyField label="Energy (kcal)" value={readOnly.energyKcal ? Math.round(readOnly.energyKcal) : '—'} />
              <ReadonlyField label="Protein (g)" value={readOnly.proteinG ? Math.round(readOnly.proteinG) : '—'} />
              <ReadonlyField label="Fat (g)" value={readOnly.fatG ? Math.round(readOnly.fatG) : '—'} />
              <ReadonlyField label="Carbs (g)" value={readOnly.carbsG ? Math.round(readOnly.carbsG) : '—'} />
            </>
          ),
        }
      ]}
    />
  )
}

export default function EditServingPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-slate-500">Loading form...</div>}>
      <EditServingForm />
    </Suspense>
  )
}
