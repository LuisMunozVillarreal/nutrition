import { gql } from '@/lib/graphql'

export const PRODUCTS_QUERY = gql`
  query SearchProducts {
    foodProducts {
      id name brand size sizeUnit
    }
  }
`

export interface FoodProduct {
  id: string
  name: string
  brand: string | null
  size: number
  sizeUnit: string
}

export function filterProducts(products: FoodProduct[], query: string): FoodProduct[] {
  const term = query.trim().toLowerCase()
  return products.filter((product) =>
    `${product.brand ?? ''} ${product.name}`.toLowerCase().includes(term),
  )
}
