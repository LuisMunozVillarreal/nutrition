'use client'

import { useEffect, useState } from 'react'

import { useSession } from 'next-auth/react'
import { graphqlRequest } from '@/lib/graphql'
import { filterProducts, PRODUCTS_QUERY, type FoodProduct } from '@/lib/productSearch'
import DataTable, { Column } from '@/components/DataTable'

const columns: Column<FoodProduct>[] = [
  { key: 'brand', label: 'Brand', accessor: (r) => r.brand || '—' },
  { key: 'name', label: 'Name', accessor: (r) => r.name },
  { key: 'size', label: 'Default Size', accessor: (r) => `${r.size} ${r.sizeUnit}` },
]

export default function ProductsPage() {
  const [data, setData] = useState<FoodProduct[]>([])
  const [query, setQuery] = useState('')
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
      <div className="mb-6">
        <h1 className="page-title" data-testid="products-title">
          Food Products
        </h1>
      </div>
      <div className="mb-4">
        <label htmlFor="product-search" className="mb-1 block text-sm font-medium">Search products</label>
        <input
          id="product-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Name or brand"
          className="w-full rounded-lg border border-slate-300 px-3 py-2"
        />
      </div>
      <DataTable
        columns={columns}
        data={filterProducts(data, query)}
        loading={loading}
        rowHref={isStaff ? (r) => `/products/${r.id}` : undefined}
        addHref={isStaff ? '/products/new' : undefined}
        addLabel="New Product"
        emptyMessage={query.trim() ? 'No products match your search.' : 'No food products available yet.'}
      />
    </div>
  )
}
