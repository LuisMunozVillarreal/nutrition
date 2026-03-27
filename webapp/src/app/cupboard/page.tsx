'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import DataTable, { Column } from '@/components/DataTable'

const CUPBOARD_QUERY = gql`
  query {
    cupboardItems {
      id foodId foodLabel started finished purchasedAt
      consumedPerc consumedServings remainingServings
    }
  }
`

interface CupboardItem {
  id: string
  foodLabel: string
  purchasedAt: string
  consumedPerc: number
  remainingServings: number
  finished: boolean
}

const columns: Column<CupboardItem>[] = [
  { key: 'food', label: 'Item', accessor: (r) => r.foodLabel },
  { key: 'purchasedAt', label: 'Purchased', accessor: (r) => new Date(r.purchasedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) },
  { key: 'status', label: 'Status', accessor: (r) => r.finished ? 'Finished' : `${Math.round(r.consumedPerc)}%` },
  { key: 'remaining', label: 'Remaining', accessor: (r) => `${r.remainingServings.toFixed(1)} servings` },
]

export default function CupboardPage() {
  const [data, setData] = useState<CupboardItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const res = await graphqlRequest<{ cupboardItems: CupboardItem[] }>(CUPBOARD_QUERY)
        setData(res.cupboardItems)
      } catch (err) { console.error('Failed to fetch cupboard items', err) }
      setLoading(false)
    }
    fetchData()
  }, [])

  return (
    <div>
      <h1 className="page-title mb-6" data-testid="cupboard-title">Cupboard</h1>
      <DataTable
        columns={columns}
        data={data}
        loading={loading}
        rowHref={(r) => `/cupboard/${r.id}`}
        addHref="/cupboard/new"
        addLabel="Add to Cupboard"
        emptyMessage="Your cupboard is empty."
      />
    </div>
  )
}
