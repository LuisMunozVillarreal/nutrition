'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { graphqlRequest, gql } from '@/lib/graphql'
import { optionalNumberInput, optionalNumberVariable } from '@/lib/optionalNumber'
import EntityForm from '@/components/EntityForm'
import { FormField, ReadonlyField } from '@/components/FormField'

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
  mutation UpdateMeasurement($id: ID!, $bodyFatPerc: Float, $weight: Float!) {
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
  const [loadStatus, setLoadStatus] = useState<'loading' | 'ready' | 'not-found' | 'error'>('loading')

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{
          measurement: {
            id: string
            bodyFatPerc: number | null
            weight: number
            bmr: number | null
            createdAt: string | null
          } | null
        }>(MEASUREMENT_QUERY, { id })

        if (res.measurement) {
          setForm({
            bodyFatPerc: optionalNumberInput(res.measurement.bodyFatPerc),
            weight: String(res.measurement.weight),
          })
          setBmr(res.measurement.bmr)
          setCreatedAt(res.measurement.createdAt)
          setLoadStatus('ready')
        } else {
          setLoadStatus('not-found')
        }
      } catch (err) {
        console.error('Failed to fetch measurement', err)
        setLoadStatus('error')
      }
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
        bodyFatPerc: optionalNumberVariable(form.bodyFatPerc),
        weight: parseFloat(form.weight),
      })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    await graphqlRequest(DELETE_MUTATION, { id })
  }

  if (loadStatus === 'loading') {
    return <div className="p-12 text-center text-slate-500">Loading...</div>
  }
  if (loadStatus === 'not-found') return <div className="p-12 text-center text-slate-500">Measurement not found.</div>
  if (loadStatus === 'error') return <div className="p-12 text-center text-red-600">Unable to load measurement.</div>

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
                min="0.1"
                max="99.9"
                value={form.bodyFatPerc}
                onChange={handleChange}
              />
              <FormField
                label="Weight (kg)"
                name="weight"
                type="number"
                step="0.1"
                min="0.1"
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
