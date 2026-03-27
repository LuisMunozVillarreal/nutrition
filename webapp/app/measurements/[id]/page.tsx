'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { graphqlRequest, gql } from '@/app/lib/graphql'
import EntityForm from '@/app/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/app/components/FormField'

const MEASUREMENT_QUERY = gql`
  query GetMeasurement($id: ID!) {
    measurement(id: $id) {
      id
      bodyFatPerc
      weight
      bmr
      createdAt
    }
  }
`

const UPDATE_MUTATION = gql`
  mutation UpdateMeasurement($id: ID!, $bodyFatPerc: Float!, $weight: Float!) {
    updateMeasurement(id: $id, bodyFatPerc: $bodyFatPerc, weight: $weight) {
      id
    }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteMeasurement($id: ID!) {
    deleteMeasurement(id: $id)
  }
`

export default function EditMeasurementPage() {
  const params = useParams()
  const id = params.id as string
  const [form, setForm] = useState({
    bodyFatPerc: '',
    weight: '',
  })
  const [bmr, setBmr] = useState<number | null>(null)
  const [createdAt, setCreatedAt] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{
          measurement: {
            id: string
            bodyFatPerc: number
            weight: number
            bmr: number
            createdAt: string
          } | null
        }>(MEASUREMENT_QUERY, { id })

        if (res.measurement) {
          setForm({
            bodyFatPerc: String(res.measurement.bodyFatPerc),
            weight: String(res.measurement.weight),
          })
          setBmr(res.measurement.bmr)
          setCreatedAt(res.measurement.createdAt)
        }
      } catch (err) {
        console.error('Failed to fetch measurement', err)
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
        weight: parseFloat(form.weight),
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
      title="Edit Measurement"
      backHref="/measurements"
      onSave={handleSave}
      onDelete={handleDelete}
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
                value={bmr !== null ? Math.round(bmr) : '—'}
                testId="field-bmr"
              />
              <ReadonlyField
                label="Created At"
                value={createdAt ? new Date(createdAt).toLocaleString() : '—'}
                testId="field-createdAt"
              />
            </>
          ),
        },
      ]}
    />
  )
}
