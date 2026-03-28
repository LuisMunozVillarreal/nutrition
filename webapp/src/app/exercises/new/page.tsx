'use client'

import { useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/components/FormField'

const CREATE_MUTATION = gql`
  mutation CreateExercise(
    $dayId: Int!, $type: String!, $kcals: Int!,
    $time: String, $duration: String, $distance: Float
  ) {
    createExercise(
      dayId: $dayId, type: $type, kcals: $kcals,
      time: $time, duration: $duration, distance: $distance
    ) { id }
  }
`

const EXERCISE_TYPES = [
  { value: 'walk', label: 'Walk' },
  { value: 'run', label: 'Run' },
  { value: 'cycle', label: 'Cycle' },
  { value: 'gym', label: 'Gym' },
]

export default function NewExercisePage() {
  const [form, setForm] = useState({
    dayId: '',
    type: 'walk',
    kcals: '',
    time: '00:00',
    duration: '',
    distance: '',
  })
  const [saving, setSaving] = useState(false)

  const handleChange = (name: string, value: string) => {
    setForm(prev => ({ ...prev, [name]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(CREATE_MUTATION, {
        dayId: parseInt(form.dayId),
        type: form.type,
        kcals: parseInt(form.kcals),
        time: form.time || '00:00',
        duration: form.duration || null,
        distance: form.distance ? parseFloat(form.distance) : null,
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <EntityForm
      title="New Exercise"
      backHref="/exercises"
      onSave={handleSave}
      saving={saving}
      fieldsets={[
        {
          title: 'Exercise Details',
          content: (
            <>
              <FormField label="Day ID" name="dayId" type="number" value={form.dayId} onChange={handleChange} required />
              <SelectField label="Type" name="type" value={form.type} onChange={handleChange} options={EXERCISE_TYPES} required />
              <FormField label="Kcals" name="kcals" type="number" value={form.kcals} onChange={handleChange} required />
              <FormField label="Time" name="time" type="time" value={form.time} onChange={handleChange} />
              <FormField label="Duration (hh:mm:ss)" name="duration" value={form.duration} onChange={handleChange} placeholder="01:30:00" />
              <FormField label="Distance (km)" name="distance" type="number" step="0.01" value={form.distance} onChange={handleChange} />
            </>
          ),
        },
      ]}
    />
  )
}
