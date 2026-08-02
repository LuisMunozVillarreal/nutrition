'use client'

import { useEffect, useRef, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/components/EntityForm'
import { FormField, ReadonlyField } from '@/components/FormField'
import {
  loadAndPrefillPreviousBodyFat,
} from './measurementForm'

const PREVIOUS_BODY_FAT_QUERY = gql`
  query GetPreviousBodyFat {
    latestMeasurement {
      bodyFatPerc
    }
  }
`

const CREATE_MUTATION = gql`
  mutation CreateMeasurement($bodyFatPerc: Float!, $weight: Float!) {
    createMeasurement(bodyFatPerc: $bodyFatPerc, weight: $weight) {
      id
    }
  }
`

interface PreviousBodyFatResponse {
  latestMeasurement: {
    bodyFatPerc: number
  } | null
}

export default function NewMeasurementPage() {
  const [form, setForm] = useState({
    bodyFatPerc: '',
    weight: '',
  })
  const [saving, setSaving] = useState(false)
  const bodyFatTouched = useRef(false)

  useEffect(() => {
    let cancelled = false

    void loadAndPrefillPreviousBodyFat({
      lookup: async () => {
        const result = await graphqlRequest<PreviousBodyFatResponse>(
          PREVIOUS_BODY_FAT_QUERY,
        )
        return result.latestMeasurement?.bodyFatPerc ?? null
      },
      updateForm: setForm,
      isTouched: () => bodyFatTouched.current,
      isCancelled: () => cancelled,
      onError: (error) => {
        console.error('Failed to load the previous body fat percentage', error)
      },
    })

    return () => {
      cancelled = true
    }
  }, [])

  const handleChange = (name: string, value: string) => {
    if (name === 'bodyFatPerc') bodyFatTouched.current = true
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
                min="0.1"
                max="99.9"
                value={form.bodyFatPerc}
                onChange={handleChange}
                required
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
