'use client'

import { useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/components/FormField'

const DATA_QUERY = gql`
  query {
    foodProducts { id name brand }
    recipes { id name brand }
  }
`

const CREATE_MUTATION = gql`
  mutation CreateCupboardItem($foodId: ID!, $purchasedAt: String!, $consumedPerc: Float!) {
    createCupboardItem(foodId: $foodId, purchasedAt: $purchasedAt, consumedPerc: $consumedPerc) { id }
  }
`

export default function NewCupboardItemPage() {
  const [foods, setFoods] = useState<{ value: string, label: string }[]>([])
  const [form, setForm] = useState({
    foodId: '',
    purchasedAt: new Date().toISOString().split('T')[0],
    consumedPerc: '0'
  })
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{ foodProducts: any[], recipes: any[] }>(DATA_QUERY)
        const options = [
          ...res.foodProducts.map(p => ({ value: p.id, label: `Product: ${p.brand ? p.brand + ' ' : ''}${p.name}` })),
          ...res.recipes.map(r => ({ value: r.id, label: `Recipe: ${r.brand ? r.brand + ' ' : ''}${r.name}` }))
        ].sort((a, b) => a.label.localeCompare(b.label))
        setFoods(options)
        if (options.length > 0) setForm(prev => ({ ...prev, foodId: options[0].value }))
      } catch (err) { console.error('Failed to fetch foods', err) }
      setLoading(false)
    }
    fetchData()
  }, [])

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(CREATE_MUTATION, {
        foodId: form.foodId,
        purchasedAt: new Date(form.purchasedAt).toISOString(),
        consumedPerc: parseFloat(form.consumedPerc)
      })
    } finally { setSaving(false) }
  }

  if (loading) return <div className="p-12 text-center text-slate-500">Loading foods...</div>

  return (
    <EntityForm
      title="Add to Cupboard"
      backHref="/cupboard"
      onSave={handleSave}
      saving={saving}
      fieldsets={[
        {
          title: 'Item Details',
          content: (
            <>
              <SelectField label="Food Item" name="foodId" value={form.foodId} onChange={handleChange} options={foods} required />
              <FormField label="Purchased At" name="purchasedAt" type="date" value={form.purchasedAt} onChange={handleChange} required />
              <FormField label="Consumed Percentage (%)" name="consumedPerc" type="number" step="1" min="0" max="100" value={form.consumedPerc} onChange={handleChange} required />
            </>
          ),
        }
      ]}
    />
  )
}
