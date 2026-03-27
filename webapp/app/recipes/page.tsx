'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/app/lib/graphql'
import DataTable, { Column } from '@/app/components/DataTable'

const RECIPES_QUERY = gql`
  query {
    recipes {
      id name numServings energyKcal proteinG fatG carbsG
    }
  }
`

interface Recipe {
  id: string
  name: string
  numServings: number
  energyKcal: number
  proteinG: number
  fatG: number
  carbsG: number
}

const columns: Column<Recipe>[] = [
  { key: 'name', label: 'Name', accessor: (r) => r.name },
  { key: 'servings', label: 'Servings', accessor: (r) => r.numServings },
  { key: 'energy', label: 'Energy (kcal)', accessor: (r) => Math.round(r.energyKcal) },
  { key: 'protein', label: 'Protein (g)', accessor: (r) => Math.round(r.proteinG) },
  { key: 'fat', label: 'Fat (g)', accessor: (r) => Math.round(r.fatG) },
  { key: 'carbs', label: 'Carbs (g)', accessor: (r) => Math.round(r.carbsG) },
]

export default function RecipesPage() {
  const [data, setData] = useState<Recipe[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const res = await graphqlRequest<{ recipes: Recipe[] }>(RECIPES_QUERY)
        setData(res.recipes)
      } catch (err) { console.error('Failed to fetch recipes', err) }
      setLoading(false)
    }
    fetchData()
  }, [])

  return (
    <div>
      <h1 className="page-title mb-6" data-testid="recipes-title">Recipes</h1>
      <DataTable
        columns={columns}
        data={data}
        loading={loading}
        rowHref={(r) => `/recipes/${r.id}`}
        addHref="/recipes/new"
        addLabel="New Recipe"
        emptyMessage="No recipes available yet."
      />
    </div>
  )
}
