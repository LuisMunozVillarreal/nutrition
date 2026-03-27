'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/app/lib/graphql'
import DataTable, { Column } from '@/app/components/DataTable'

const EXERCISES_QUERY = gql`
  query {
    exercises {
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

const DELETE_MUTATION = gql`
  mutation DeleteExercise($id: ID!) {
    deleteExercise(id: $id)
  }
`

interface Exercise {
  id: string
  dayId: number
  time: string
  type: string
  kcals: number
  duration: string | null
  distance: number | null
}

const columns: Column<Exercise>[] = [
  { key: 'id', label: 'ID', accessor: (r) => r.id },
  { key: 'type', label: 'Type', accessor: (r) => r.type.charAt(0).toUpperCase() + r.type.slice(1) },
  { key: 'kcals', label: 'Kcals', accessor: (r) => r.kcals },
  { key: 'duration', label: 'Duration', accessor: (r) => r.duration || '—' },
  { key: 'distance', label: 'Distance (km)', accessor: (r) => r.distance ?? '—' },
  { key: 'time', label: 'Time', accessor: (r) => r.time },
]

export default function ExercisesPage() {
  const [data, setData] = useState<Exercise[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await graphqlRequest<{ exercises: Exercise[] }>(EXERCISES_QUERY)
      setData(res.exercises)
    } catch (err) {
      console.error('Failed to fetch exercises', err)
    }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])

  const handleDelete = async (row: Exercise) => {
    if (!confirm('Delete this exercise?')) return
    try {
      await graphqlRequest(DELETE_MUTATION, { id: row.id })
      fetchData()
    } catch (err) {
      console.error('Failed to delete exercise', err)
    }
  }

  return (
    <div>
      <h1 className="page-title mb-6" data-testid="exercises-title">Exercises</h1>
      <DataTable
        columns={columns}
        data={data}
        loading={loading}
        rowHref={(r) => `/exercises/${r.id}`}
        addHref="/exercises/new"
        addLabel="New Exercise"
        onDelete={handleDelete}
        emptyMessage="No exercises logged yet."
      />
    </div>
  )
}
