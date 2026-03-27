'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import DataTable, { Column } from '@/app/components/DataTable'

const STEPS_QUERY = gql`
  query {
    dayStepsList {
      id
      dayId
      steps
      kcals
    }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteDaySteps($id: ID!) {
    deleteDaySteps(id: $id)
  }
`

interface DayStepsRow {
  id: string
  dayId: number
  steps: number
  kcals: number
}

const columns: Column<DayStepsRow>[] = [
  { key: 'id', label: 'ID', accessor: (r) => r.id },
  { key: 'dayId', label: 'Day', accessor: (r) => r.dayId },
  { key: 'steps', label: 'Steps', accessor: (r) => r.steps.toLocaleString() },
  { key: 'kcals', label: 'Kcals', accessor: (r) => Math.round(r.kcals) },
]

export default function StepsPage() {
  const [data, setData] = useState<DayStepsRow[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await graphqlRequest<{ dayStepsList: DayStepsRow[] }>(STEPS_QUERY)
      setData(res.dayStepsList)
    } catch (err) { console.error('Failed to fetch steps', err) }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])

  const handleDelete = async (row: DayStepsRow) => {
    if (!confirm('Delete this steps record?')) return
    try {
      await graphqlRequest(DELETE_MUTATION, { id: row.id })
      fetchData()
    } catch (err) { console.error('Failed to delete steps', err) }
  }

  return (
    <div>
      <h1 className="page-title mb-6" data-testid="steps-title">Day Steps</h1>
      <DataTable
        columns={columns}
        data={data}
        loading={loading}
        rowHref={(r) => `/steps/${r.id}`}
        addHref="/steps/new"
        addLabel="New Steps Record"
        onDelete={handleDelete}
        emptyMessage="No step records yet."
      />
    </div>
  )
}
