'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/app/lib/graphql'
import DataTable, { Column } from '@/app/components/DataTable'

const PRODUCTS_QUERY = gql`
  query {
    foodProducts {
      id name brand size sizeUnit
    }
  }
`

interface FoodProduct {
  id: string
  name: string
  brand: string | null
  size: number
  sizeUnit: string
}

const columns: Column<FoodProduct>[] = [
  { key: 'brand', label: 'Brand', accessor: (r) => r.brand || '—' },
  { key: 'name', label: 'Name', accessor: (r) => r.name },
  { key: 'size', label: 'Default Size', accessor: (r) => `${r.size} ${r.sizeUnit}` },
]

export default function ProductsPage() {
  const [data, setData] = useState<FoodProduct[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const res = await graphqlRequest<{ foodProducts: FoodProduct[] }>(PRODUCTS_QUERY)
        setData(res.foodProducts)
      } catch (err) { console.error('Failed to fetch food products', err) }
      setLoading(false)
    }
    fetchData()
  }, [])

  return (
    <div>
      <h1 className="page-title mb-6" data-testid="products-title">Food Products</h1>
      <DataTable
        columns={columns}
        data={data}
        loading={loading}
        rowHref={(r) => `/products/${r.id}`}
        addHref="/products/new"
        addLabel="New Product"
        emptyMessage="No food products available yet."
      />
    </div>
  )
}
