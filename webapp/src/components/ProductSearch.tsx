'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest } from '@/lib/graphql'
import { filterProducts, PRODUCTS_QUERY, type FoodProduct } from '@/lib/productSearch'

export default function ProductSearch({ onSelect, onSearchStart }: {
  onSelect: (product: FoodProduct) => void
  onSearchStart: () => void
}) {
  const [query, setQuery] = useState('')
  const [started, setStarted] = useState(false)
  const [products, setProducts] = useState<FoodProduct[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!started) return
    let cancelled = false
    void graphqlRequest<{ foodProducts: FoodProduct[] }>(PRODUCTS_QUERY)
      .then((result) => { if (!cancelled) setProducts(result.foodProducts) })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
  }, [started, attempt])

  const matches = filterProducts(products ?? [], query)
  return (
    <section className="mb-6" aria-label="Find an existing product">
      <label htmlFor="product-search" className="mb-1 block text-sm font-medium">Search products</label>
      <input
        id="product-search"
        type="search"
        value={query}
        onFocus={onSearchStart}
        onChange={(event) => {
          setQuery(event.target.value)
          if (event.target.value.trim()) setStarted(true)
        }}
        placeholder="Name or brand"
        className="w-full rounded-lg border border-slate-300 px-3 py-2"
      />
      {query.trim() && (
        <div className="mt-3 grid max-h-72 gap-2 overflow-y-auto" aria-live="polite">
          {failed ? (
            <div role="alert">
              <p>Could not load products. Try again.</p>
              <button type="button" className="underline" onClick={() => {
                setFailed(false)
                setAttempt((value) => value + 1)
              }}>Retry product search</button>
            </div>
          ) : products === null && <p role="status">Loading products...</p>}
          {products !== null && matches.length === 0 && <p role="status">No products match your search.</p>}
          {matches.map((product) => (
            <button
              key={product.id}
              type="button"
              onClick={() => onSelect(product)}
              className="rounded-lg border border-slate-300 p-3 text-left hover:bg-slate-50"
            >
              <span className="block font-medium">Select {product.brand ? `${product.brand} ` : ''}{product.name}</span>
              <span className="block text-sm text-slate-500">{product.size} {product.sizeUnit}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
