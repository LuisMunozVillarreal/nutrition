'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '../../lib/graphql'
import DataTable, { Column } from '../../components/DataTable'

const GOALS_QUERY = gql`
  query {
    fatPercGoals {
      id
      bodyFatPerc
      createdAt
    }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteFatPercGoal($id: ID!) {
    deleteFatPercGoal(id: $id)
  }
`

interface FatPercGoal {
  id: string
  bodyFatPerc: number
  createdAt: string
}

const columns: Column<FatPercGoal>[] = [
  { key: 'id', label: 'ID', accessor: (r) => r.id },
  {
    key: 'createdAt',
    label: 'Date',
    accessor: (r) => new Date(r.createdAt).toLocaleDateString(),
  },
  { key: 'bodyFatPerc', label: 'Body Fat % Goal', accessor: (r) => r.bodyFatPerc },
]

export default function GoalsPage() {
  const [data, setData] = useState<FatPercGoal[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await graphqlRequest<{ fatPercGoals: FatPercGoal[] }>(GOALS_QUERY)
      setData(res.fatPercGoals)
    } catch (err) {
      console.error('Failed to fetch goals', err)
    }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])

  const handleDelete = async (row: FatPercGoal) => {
    if (!confirm('Delete this goal?')) return
    try {
      await graphqlRequest(DELETE_MUTATION, { id: row.id })
      fetchData()
    } catch (err) {
      console.error('Failed to delete goal', err)
    }
  }

  return (
    <div>
      <h1 className="page-title mb-6" data-testid="goals-title">Body Fat % Goals</h1>
      <DataTable
        columns={columns}
        data={data}
        loading={loading}
        rowHref={(r) => `/goals/${r.id}`}
        addHref="/goals/new"
        addLabel="New Goal"
        onDelete={handleDelete}
        emptyMessage="No goals set yet. Add your first one!"
      />
    </div>
  )
}
