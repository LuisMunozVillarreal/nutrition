'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { graphqlRequest, gql } from '@/app/lib/graphql'
import EntityForm from '@/app/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/app/components/FormField'

const GOAL_QUERY = gql`
  query GetGoal($id: ID!) {
    fatPercGoal(id: $id) {
      id
      bodyFatPerc
      createdAt
    }
  }
`

const UPDATE_MUTATION = gql`
  mutation UpdateFatPercGoal($id: ID!, $bodyFatPerc: Float!) {
    updateFatPercGoal(id: $id, bodyFatPerc: $bodyFatPerc) {
      id
    }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteFatPercGoal($id: ID!) {
    deleteFatPercGoal(id: $id)
  }
`

export default function EditGoalPage() {
  const params = useParams()
  const id = params.id as string
  const [form, setForm] = useState({ bodyFatPerc: '' })
  const [createdAt, setCreatedAt] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{
          fatPercGoal: { id: string; bodyFatPerc: number; createdAt: string } | null
        }>(GOAL_QUERY, { id })
        if (res.fatPercGoal) {
          setForm({ bodyFatPerc: String(res.fatPercGoal.bodyFatPerc) })
          setCreatedAt(res.fatPercGoal.createdAt)
        }
      } catch (err) {
        console.error('Failed to fetch goal', err)
      }
      setLoading(false)
    }
    fetchData()
  }, [id])

  const handleChange = (name: string, value: string) => {
    setForm(prev => ({ ...prev, [name]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(UPDATE_MUTATION, {
        id,
        bodyFatPerc: parseFloat(form.bodyFatPerc),
      })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    await graphqlRequest(DELETE_MUTATION, { id })
  }

  if (loading) {
    return <div className="p-12 text-center text-slate-500">Loading...</div>
  }

  return (
    <EntityForm
      title="Edit Body Fat % Goal"
      backHref="/goals"
      onSave={handleSave}
      onDelete={handleDelete}
      saving={saving}
      fieldsets={[
        {
          title: 'Goal Details',
          content: (
            <>
              <FormField
                label="Body Fat % Goal"
                name="bodyFatPerc"
                type="number"
                step="0.1"
                value={form.bodyFatPerc}
                onChange={handleChange}
                required
              />
              <ReadonlyField
                label="Created At"
                value={createdAt ? new Date(createdAt).toLocaleString() : '—'}
              />
            </>
          ),
        },
      ]}
    />
  )
}
