'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import DataTable, { Column } from '@/app/components/DataTable'

const DAYS_QUERY = gql`
  query {
    weekPlans {
      days {
        id day dayNum completed energyKcalGoal energyKcal
      }
    }
  }
`

interface DayRow {
  id: string
  day: string
  dayNum: number
  completed: boolean
  energyKcalGoal: number
  energyKcal: number
}

const columns: Column<DayRow>[] = [
  { key: 'id', label: 'ID', accessor: (r) => r.id },
  { key: 'day', label: 'Date', accessor: (r) => r.day },
  { key: 'completed', label: 'Done', accessor: (r) => r.completed ? 'Yes' : 'No' },
  { key: 'energy', label: 'Energy', accessor: (r) => `${Math.round(r.energyKcal)} / ${Math.round(r.energyKcalGoal)} kcal` },
]

export default function DaysPage() {
  const [data, setData] = useState<DayRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const res = await graphqlRequest<{ weekPlans: { days: DayRow[] }[] }>(DAYS_QUERY)
        const allDays = res.weekPlans.flatMap(p => p.days)
        // Sort descending by date
        allDays.sort((a, b) => b.day.localeCompare(a.day))
        setData(allDays)
      } catch (err) { console.error('Failed to fetch days', err) }
      setLoading(false)
    }
    fetchData()
  }, [])

  return (
    <div>
      <h1 className="page-title mb-6" data-testid="days-title">Days</h1>
      <p className="text-sm text-slate-400 mb-6">Days are automatically generated when you create a Week Plan. Click a row to view and log intakes.</p>
      <DataTable
        columns={columns}
        data={data}
        loading={loading}
        rowHref={(r) => `/days/${r.id}`}
        emptyMessage="No days available yet."
      />
    </div>
  )
}
