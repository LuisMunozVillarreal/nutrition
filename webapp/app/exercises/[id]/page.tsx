'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { graphqlRequest, gql } from '@/app/lib/graphql'
import EntityForm from '@/app/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/app/components/FormField'

const EXERCISE_QUERY = gql`
  query GetExercise($id: ID!) {
    exercise(id: $id) {
      id
      dayId
      time
      type
      kcals
      duration
      distance
    }
  }
`

const UPDATE_MUTATION = gql`
  mutation UpdateExercise(
    $id: ID!, $type: String!, $kcals: Int!,
    $time: String, $duration: String, $distance: Float
  ) {
    updateExercise(
      id: $id, type: $type, kcals: $kcals,
      time: $time, duration: $duration, distance: $distance
    ) { id }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteExercise($id: ID!) {
    deleteExercise(id: $id)
  }
`

const EXERCISE_TYPES = [
  { value: 'walk', label: 'Walk' },
  { value: 'run', label: 'Run' },
  { value: 'cycle', label: 'Cycle' },
  { value: 'gym', label: 'Gym' },
]

export default function EditExercisePage() {
  const params = useParams()
  const id = params.id as string
  const [form, setForm] = useState({
    type: 'walk', kcals: '', time: '00:00', duration: '', distance: '',
  })
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{ exercise: { type: string; kcals: number; time: string; duration: string | null; distance: number | null } | null }>(EXERCISE_QUERY, { id })
        if (res.exercise) {
          setForm({
            type: res.exercise.type,
            kcals: String(res.exercise.kcals),
            time: res.exercise.time.substring(0, 5),
            duration: res.exercise.duration || '',
            distance: res.exercise.distance ? String(res.exercise.distance) : '',
          })
        }
      } catch (err) { console.error('Failed to fetch exercise', err) }
      setLoading(false)
    }
    fetchData()
  }, [id])

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(UPDATE_MUTATION, {
        id, type: form.type, kcals: parseInt(form.kcals),
        time: form.time || '00:00',
        duration: form.duration || null,
        distance: form.distance ? parseFloat(form.distance) : null,
      })
    } finally { setSaving(false) }
  }

  const handleDelete = async () => { await graphqlRequest(DELETE_MUTATION, { id }) }

  if (loading) return <div className="p-12 text-center text-slate-500">Loading...</div>

  return (
    <EntityForm
      title="Edit Exercise"
      backHref="/exercises"
      onSave={handleSave}
      onDelete={handleDelete}
      saving={saving}
      fieldsets={[{
        title: 'Exercise Details',
        content: (
          <>
            <SelectField label="Type" name="type" value={form.type} onChange={handleChange} options={EXERCISE_TYPES} required />
            <FormField label="Kcals" name="kcals" type="number" value={form.kcals} onChange={handleChange} required />
            <FormField label="Time" name="time" type="time" value={form.time} onChange={handleChange} />
            <FormField label="Duration (hh:mm:ss)" name="duration" value={form.duration} onChange={handleChange} placeholder="01:30:00" />
            <FormField label="Distance (km)" name="distance" type="number" step="0.01" value={form.distance} onChange={handleChange} />
          </>
        ),
      }]}
    />
  )
}
