'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { graphqlRequest, gql } from '../../../lib/graphql'
import EntityForm from '../../components/EntityForm'
import { FormField } from '../../components/FormField'

const ITEM_QUERY = gql`
  query GetCupboardItem($id: ID!) {
    cupboardItem(id: $id) {
      id foodId foodLabel purchasedAt consumedPerc
    }
  }
`

const UPDATE_MUTATION = gql`
  mutation UpdateCupboardItem($id: ID!, $consumedPerc: Float!) {
    updateCupboardItem(id: $id, consumedPerc: $consumedPerc) { id }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteCupboardItem($id: ID!) {
    deleteCupboardItem(id: $id)
  }
`

export default function EditCupboardItemPage() {
  const params = useParams()
  const id = params.id as string
  const [item, setItem] = useState<any>(null)
  const [form, setForm] = useState({ consumedPerc: '' })
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{ cupboardItem: any }>(ITEM_QUERY, { id })
        if (res.cupboardItem) {
          setItem(res.cupboardItem)
          setForm({ consumedPerc: String(res.cupboardItem.consumedPerc) })
        }
      } catch (err) { console.error('Failed to fetch item', err) }
      setLoading(false)
    }
    fetchData()
  }, [id])

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(UPDATE_MUTATION, {
        id,
        consumedPerc: parseFloat(form.consumedPerc)
      })
    } finally { setSaving(false) }
  }

  const handleDelete = async () => { await graphqlRequest(DELETE_MUTATION, { id }) }

  if (loading) return <div className="p-12 text-center text-slate-500">Loading...</div>
  if (!item) return <div className="p-12 text-center text-red-500">Item not found.</div>

  return (
    <EntityForm
      title={`Edit ${item.foodLabel}`}
      backHref="/cupboard"
      onSave={handleSave}
      onDelete={handleDelete}
      saving={saving}
      fieldsets={[
        {
          title: 'Inventory Status',
          content: (
            <>
              <div className="mb-4 text-sm text-slate-500">
                Purchased on: {new Date(item.purchasedAt).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
              </div>
              <FormField label="Consumed Percentage (%)" name="consumedPerc" type="number" step="1" min="0" max="100" value={form.consumedPerc} onChange={handleChange} required />
              <div className="mt-4 h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-indigo-500 transition-all duration-500" 
                  style={{ width: `${form.consumedPerc}%` }}
                />
              </div>
            </>
          ),
        }
      ]}
    />
  )
}
