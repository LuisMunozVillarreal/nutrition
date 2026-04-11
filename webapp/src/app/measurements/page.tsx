'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import DataTable, { Column } from '@/components/DataTable'

const MEASUREMENTS_QUERY = gql`
  query {
    measurements {
      id
      bodyFatPerc
      weight
      bmr
      createdAt
    }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteMeasurement($id: ID!) {
    deleteMeasurement(id: $id)
  }
`

interface Measurement {
  id: string
  bodyFatPerc: number
  weight: number
  bmr: number
  createdAt: string
}

const columns: Column<Measurement>[] = [
  { key: 'id', label: 'ID', accessor: (r) => r.id },
  {
    key: 'createdAt',
    label: 'Date',
    accessor: (r) => new Date(r.createdAt).toLocaleDateString(),
  },
  { key: 'bodyFatPerc', label: 'Body Fat (%)', accessor: (r) => r.bodyFatPerc },
  { key: 'weight', label: 'Weight (kg)', accessor: (r) => r.weight },
  { key: 'bmr', label: 'BMR', accessor: (r) => Math.round(r.bmr) },
]

export default function MeasurementsPage() {
  const [data, setData] = useState<Measurement[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await graphqlRequest<{ measurements: Measurement[] }>(MEASUREMENTS_QUERY)
      setData(res.measurements)
    } catch (err) {
      console.error('Failed to fetch measurements', err)
    }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])

  const handleDelete = async (row: Measurement) => {
    if (!confirm('Delete this measurement?')) return
    try {
      await graphqlRequest(DELETE_MUTATION, { id: row.id })
      fetchData()
    } catch (err) {
      console.error('Failed to delete measurement', err)
    }
  }

  return (
    <div>
      <h1 className="page-title mb-6" data-testid="measurements-title">Measurements</h1>
      <DataTable
        columns={columns}
        data={data}
        loading={loading}
        rowHref={(r) => `/measurements/${r.id}`}
        addHref="/measurements/new"
        addLabel="New Measurement"
        onDelete={handleDelete}
        emptyMessage="No measurements yet. Add your first one!"
      />
    </div>
  )
}
