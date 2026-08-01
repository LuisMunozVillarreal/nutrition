'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import DataTable, { Column } from '@/components/DataTable'
import { subscribeToPromise } from '@/lib/promiseSubscription'

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

  const loadData = () => graphqlRequest<{ exercises: Exercise[] }>(EXERCISES_QUERY)
  const applyData = (res: { exercises: Exercise[] }) => setData(res.exercises)
  const reportLoadError = (err: unknown) => console.error('Failed to fetch exercises', err)
  const finishLoading = () => setLoading(false)

  const reloadData = () => {
    setLoading(true)
    return loadData().then(applyData, reportLoadError).then(finishLoading)
  }

  useEffect(() => subscribeToPromise(loadData(), {
    onFulfilled: applyData,
    onRejected: reportLoadError,
    onSettled: finishLoading,
  }), [])

  const handleDelete = async (row: Exercise) => {
    if (!confirm('Delete this exercise?')) return
    try {
      await graphqlRequest(DELETE_MUTATION, { id: row.id })
      await reloadData()
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
