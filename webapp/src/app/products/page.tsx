'use client'

import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { graphqlRequest, gql } from '@/lib/graphql'
import DataTable, { Column } from '@/components/DataTable'

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
  const { data: session } = useSession()
  const isStaff = session?.user?.isStaff === true

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
        rowHref={isStaff ? (r) => `/products/${r.id}` : undefined}
        addHref={isStaff ? '/products/new' : undefined}
        addLabel="New Product"
        emptyMessage="No food products available yet."
      />
    </div>
  )
}
