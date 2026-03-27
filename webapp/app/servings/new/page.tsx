'use client'

import { useState, Suspense } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/app/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/app/components/FormField'
import { useSearchParams } from 'next/navigation'

const CREATE_MUTATION = gql`
  mutation CreateServing($foodId: ID!, $servingSize: Float!, $servingUnit: String!) {
    createServing(foodId: $foodId, servingSize: $servingSize, servingUnit: $servingUnit) { id }
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

function NewServingForm() {
  const searchParams = useSearchParams()
  const foodId = searchParams.get('foodId')
  
  const [form, setForm] = useState({
    servingSize: '1.0', servingUnit: 'serving'
  })
  const [saving, setSaving] = useState(false)

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    if (!foodId) return
    setSaving(true)
    try {
      await graphqlRequest(CREATE_MUTATION, {
        foodId,
        servingSize: parseFloat(form.servingSize),
        servingUnit: form.servingUnit,
      })
    } finally { setSaving(false) }
  }

  return (
    <EntityForm
      title="Add Serving"
      backHref={foodId ? `/products/${foodId}` : "/products"}
      onSave={handleSave}
      saving={saving}
      fieldsets={[{
        title: 'Serving Details',
        content: (
          <>
            <div className="grid grid-cols-2 gap-4">
              <FormField label="Size" name="servingSize" type="number" step="0.1" value={form.servingSize} onChange={handleChange} required />
              <SelectField label="Unit" name="servingUnit" value={form.servingUnit} onChange={handleChange} options={UNIT_CHOICES} required />
            </div>
          </>
        ),
      }]}
    />
  )
}

export default function NewServingPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-slate-500">Loading form...</div>}>
      <NewServingForm />
    </Suspense>
  )
}
