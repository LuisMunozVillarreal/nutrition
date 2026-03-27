'use client'

import { useState } from 'react'
import { graphqlRequest, gql } from '../../../lib/graphql'
import EntityForm from '../../components/EntityForm'
import { FormField } from '../../components/FormField'

const CREATE_MUTATION = gql`
  mutation CreateWeekPlan(
    $startDate: String!, $proteinGKg: Float!, $fatPerc: Float!,
    $deficit: Int!, $measurementId: Int!
  ) {
    createWeekPlan(
      startDate: $startDate, proteinGKg: $proteinGKg, fatPerc: $fatPerc,
      deficit: $deficit, measurementId: $measurementId
    ) { id }
  }
`

export default function NewPlanPage() {
  const [form, setForm] = useState({
    startDate: new Date().toISOString().split('T')[0],
    proteinGKg: '2.0',
    fatPerc: '25.0',
    deficit: '0',
    measurementId: '',
  })
  const [saving, setSaving] = useState(false)

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(CREATE_MUTATION, {
        startDate: form.startDate,
        proteinGKg: parseFloat(form.proteinGKg),
        fatPerc: parseFloat(form.fatPerc),
        deficit: parseInt(form.deficit),
        measurementId: parseInt(form.measurementId),
      })
    } finally { setSaving(false) }
  }

  return (
    <EntityForm
      title="New Week Plan"
      backHref="/plans"
      onSave={handleSave}
      saving={saving}
      fieldsets={[{
        title: 'Plan Details',
        content: (
          <>
            <FormField label="Start Date" name="startDate" type="date" value={form.startDate} onChange={handleChange} required />
            <FormField label="Measurement ID" name="measurementId" type="number" value={form.measurementId} onChange={handleChange} required />
            <FormField label="Protein (g/kg)" name="proteinGKg" type="number" step="0.1" value={form.proteinGKg} onChange={handleChange} required />
            <FormField label="Fat (%)" name="fatPerc" type="number" step="0.1" value={form.fatPerc} onChange={handleChange} required />
            <FormField label="Deficit (kcals)" name="deficit" type="number" value={form.deficit} onChange={handleChange} required />
          </>
        ),
      }]}
    />
  )
}
