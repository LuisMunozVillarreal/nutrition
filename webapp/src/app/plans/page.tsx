'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '../../lib/graphql'
import DataTable, { Column } from '../../components/DataTable'
import Link from 'next/link'

const PLANS_QUERY = gql`
  query {
    weekPlans {
      id
      startDate
      completed
      energyKcalGoal
      energyKcal
    }
  }
`

interface WeekPlan {
  id: string
  startDate: string
  completed: boolean
  energyKcalGoal: number
  energyKcal: number
}

const columns: Column<WeekPlan>[] = [
  { key: 'id', label: 'ID', accessor: (r) => r.id },
  { key: 'startDate', label: 'Start Date', accessor: (r) => r.startDate },
  { key: 'completed', label: 'Completed', accessor: (r) => r.completed ? 'Yes' : 'No' },
  { key: 'energyKcalGoal', label: 'Energy Goal', accessor: (r) => Math.round(r.energyKcalGoal) },
  { key: 'energyKcal', label: 'Energy Intake', accessor: (r) => Math.round(r.energyKcal) },
]

export default function PlansPage() {
  const [data, setData] = useState<WeekPlan[]>([])
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await graphqlRequest<{ weekPlans: WeekPlan[] }>(PLANS_QUERY)
      setData(res.weekPlans)
    } catch (err) { console.error('Failed to fetch plans', err) }
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])

  return (
    <div>
      <h1 className="page-title mb-6" data-testid="plans-title">Week Plans</h1>
      <DataTable
        columns={columns}
        data={data}
        loading={loading}
        rowHref={(r) => `/plans/${r.id}`}
        addHref="/plans/new"
        addLabel="New Plan"
        emptyMessage="No plans created yet."
      />
    </div>
  )
}
