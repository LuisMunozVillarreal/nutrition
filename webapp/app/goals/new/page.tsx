'use client'

import { useState } from 'react'
import { graphqlRequest, gql } from '../../../lib/graphql'
import EntityForm from '../../components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '../../components/FormField'

const CREATE_MUTATION = gql`
  mutation CreateFatPercGoal($bodyFatPerc: Float!) {
    createFatPercGoal(bodyFatPerc: $bodyFatPerc) {
      id
    }
  }
`

export default function NewGoalPage() {
  const [form, setForm] = useState({ bodyFatPerc: '' })
  const [saving, setSaving] = useState(false)

  const handleChange = (name: string, value: string) => {
    setForm(prev => ({ ...prev, [name]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(CREATE_MUTATION, {
        bodyFatPerc: parseFloat(form.bodyFatPerc),
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <EntityForm
      title="New Body Fat % Goal"
      backHref="/goals"
      onSave={handleSave}
      saving={saving}
      fieldsets={[
        {
          title: 'Goal Details',
          content: (
            <FormField
              label="Body Fat % Goal"
              name="bodyFatPerc"
              type="number"
              step="0.1"
              value={form.bodyFatPerc}
              onChange={handleChange}
              required
              helpText="Target body fat percentage."
            />
          ),
        },
      ]}
    />
  )
}
