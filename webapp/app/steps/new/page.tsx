'use client'

import { useState } from 'react'
import { graphqlRequest, gql } from '../../../lib/graphql'
import EntityForm from '../../components/EntityForm'
import { FormField, ReadonlyField } from '../../components/FormField'

const CREATE_MUTATION = gql`
  mutation CreateDaySteps($dayId: Int!, $steps: Int!) {
    createDaySteps(dayId: $dayId, steps: $steps) { id }
  }
`

export default function NewStepsPage() {
  const [form, setForm] = useState({ dayId: '', steps: '' })
  const [saving, setSaving] = useState(false)

  const handleChange = (name: string, value: string) => {
    setForm(prev => ({ ...prev, [name]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(CREATE_MUTATION, {
        dayId: parseInt(form.dayId),
        steps: parseInt(form.steps),
      })
    } finally { setSaving(false) }
  }

  return (
    <EntityForm
      title="New Day Steps"
      backHref="/steps"
      onSave={handleSave}
      saving={saving}
      fieldsets={[{
        title: 'Steps Details',
        content: (
          <>
            <FormField label="Day ID" name="dayId" type="number" value={form.dayId} onChange={handleChange} required />
            <FormField label="Steps" name="steps" type="number" value={form.steps} onChange={handleChange} required />
            <ReadonlyField label="Kcals" value="Calculated after save" />
          </>
        ),
      }]}
    />
  )
}
