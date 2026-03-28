'use client'

import { useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/components/FormField'

const CREATE_MUTATION = gql`
  mutation CreateMeasurement($bodyFatPerc: Float!, $weight: Float!) {
    createMeasurement(bodyFatPerc: $bodyFatPerc, weight: $weight) {
      id
    }
  }
`

export default function NewMeasurementPage() {
  const [form, setForm] = useState({
    bodyFatPerc: '',
    weight: '',
  })
  const [saving, setSaving] = useState(false)

  const handleChange = (name: string, value: string) => {
    setForm(prev => ({ ...prev, [name]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(CREATE_MUTATION, {
        bodyFatPerc: parseFloat(form.bodyFatPerc),
        weight: parseFloat(form.weight),
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <EntityForm
      title="New Measurement"
      backHref="/measurements"
      onSave={handleSave}
      saving={saving}
      fieldsets={[
        {
          title: 'Measurement Details',
          content: (
            <>
              <FormField
                label="Body Fat (%)"
                name="bodyFatPerc"
                type="number"
                step="0.1"
                value={form.bodyFatPerc}
                onChange={handleChange}
                required
              />
              <FormField
                label="Weight (kg)"
                name="weight"
                type="number"
                step="0.1"
                value={form.weight}
                onChange={handleChange}
                required
              />
              <ReadonlyField
                label="BMR"
                value="Calculated after save"
                testId="field-bmr"
              />
            </>
          ),
        },
      ]}
    />
  )
}
