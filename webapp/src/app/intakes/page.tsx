'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import DataTable, { Column } from '@/components/DataTable'

const QUERY = gql`
  query Intakes {
    weekPlans {
      days {
        day
        intakes { id meal numServings energyKcal proteinG fatG carbsG }
      }
    }
  }
`

interface Intake {
  id: string
  meal: string
  numServings: number
  energyKcal: number
  proteinG: number
  fatG: number
  carbsG: number
}
interface IntakeRow extends Intake { date: string }
interface Response { weekPlans: Array<{ days: Array<{ day: string; intakes: Intake[] }> }> }

const columns: Column<IntakeRow>[] = [
  { key: 'date', label: 'Date', accessor: (row) => row.date },
  { key: 'meal', label: 'Meal', accessor: (row) => row.meal },
  { key: 'numServings', label: 'Servings', accessor: (row) => row.numServings },
  { key: 'energyKcal', label: 'Energy (kcal)', accessor: (row) => row.energyKcal },
  { key: 'proteinG', label: 'Protein (g)', accessor: (row) => row.proteinG },
  { key: 'fatG', label: 'Fat (g)', accessor: (row) => row.fatG },
  { key: 'carbsG', label: 'Carbs (g)', accessor: (row) => row.carbsG },
]

export default function IntakesPage() {
  const [rows, setRows] = useState<IntakeRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const result = await graphqlRequest<Response>(QUERY)
        if (cancelled) return
        setRows(result.weekPlans.flatMap((plan) => plan.days.flatMap((day) =>
          day.intakes.map((intake) => ({ ...intake, date: day.day })),
        )).sort((a, b) => b.date.localeCompare(a.date)))
      } catch {
        if (!cancelled) setError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [])

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Intakes</h1>
      {error && <p role="alert">Unable to load intakes. Please try again.</p>}
      <DataTable
        columns={columns} data={rows} loading={loading}
        rowHref={(row) => `/intakes/${encodeURIComponent(row.id)}`}
        addHref="/intakes/new" addLabel="Log a meal"
        emptyMessage={error ? 'Intakes could not be loaded.' : 'No intakes logged yet.'}
      />
    </div>
  )
}
