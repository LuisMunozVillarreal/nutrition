'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { graphqlRequest, gql } from '../../../lib/graphql'
import EntityForm from '../../components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '../../components/FormField'

const STEPS_QUERY = gql`
  query GetDaySteps($id: ID!) {
    daySteps(id: $id) { id steps kcals }
  }
`

const UPDATE_MUTATION = gql`
  mutation UpdateDaySteps($id: ID!, $steps: Int!) {
    updateDaySteps(id: $id, steps: $steps) { id }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteDaySteps($id: ID!) {
    deleteDaySteps(id: $id)
  }
`

export default function EditStepsPage() {
  const params = useParams()
  const id = params.id as string
  const [form, setForm] = useState({ steps: '' })
  const [kcals, setKcals] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{ daySteps: { steps: number; kcals: number } | null }>(STEPS_QUERY, { id })
        if (res.daySteps) {
          setForm({ steps: String(res.daySteps.steps) })
          setKcals(res.daySteps.kcals)
        }
      } catch (err) { console.error('Failed to fetch steps', err) }
      setLoading(false)
    }
    fetchData()
  }, [id])

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(UPDATE_MUTATION, { id, steps: parseInt(form.steps) })
    } finally { setSaving(false) }
  }

  const handleDelete = async () => { await graphqlRequest(DELETE_MUTATION, { id }) }

  if (loading) return <div className="p-12 text-center text-slate-500">Loading...</div>

  return (
    <EntityForm
      title="Edit Day Steps"
      backHref="/steps"
      onSave={handleSave}
      onDelete={handleDelete}
      saving={saving}
      fieldsets={[{
        title: 'Steps Details',
        content: (
          <>
            <FormField label="Steps" name="steps" type="number" value={form.steps} onChange={handleChange} required />
            <ReadonlyField label="Kcals" value={kcals !== null ? Math.round(kcals) : '—'} />
          </>
        ),
      }]}
    />
  )
}
