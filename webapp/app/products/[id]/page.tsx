'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/app/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/app/components/FormField'
import DataTable, { Column } from '@/app/components/DataTable'

const PRODUCT_QUERY = gql`
  query GetFoodProduct($id: ID!) {
    foodProduct(id: $id) {
      id brand name barcode notes
      nutritionalInfoSize nutritionalInfoUnit
      size sizeUnit numServings
      energyKcal proteinG fatG carbsG
      saturatedFatG sugarsG fibreG saltG
      servings {
        id servingSize servingUnit energyKcal proteinG
      }
    }
  }
`

const UPDATE_MUTATION = gql`
  mutation UpdateFoodProduct(
    $id: ID!, $name: String!, $brand: String, $barcode: String, $notes: String!,
    $nutritionalInfoSize: Float!, $nutritionalInfoUnit: String!,
    $size: Float!, $sizeUnit: String!, $numServings: Float!,
    $energyKcal: Float!, $proteinG: Float!, $fatG: Float!, $carbsG: Float!,
    $saturatedFatG: Float, $sugarsG: Float, $fibreG: Float, $saltG: Float
  ) {
    updateFoodProduct(
      id: $id, name: $name, brand: $brand, barcode: $barcode, notes: $notes,
      nutritionalInfoSize: $nutritionalInfoSize, nutritionalInfoUnit: $nutritionalInfoUnit,
      size: $size, sizeUnit: $sizeUnit, numServings: $numServings,
      energyKcal: $energyKcal, proteinG: $proteinG, fatG: $fatG, carbsG: $carbsG,
      saturatedFatG: $saturatedFatG, sugarsG: $sugarsG, fibreG: $fibreG, saltG: $saltG
    ) { id }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteFoodProduct($id: ID!) {
    deleteFoodProduct(id: $id)
  }
`

const UNIT_CHOICES = [
  { value: 'g', label: 'g' },
  { value: 'ml', label: 'ml' },
  { value: 'fl oz', label: 'fl oz' },
  { value: 'oz', label: 'oz' },
  { value: 'container', label: 'container' },
  { value: 'serving', label: 'serving' },
]

interface ServingRow {
  id: string
  servingSize: number
  servingUnit: string
  energyKcal: number
  proteinG: number
}

const servingColumns: Column<ServingRow>[] = [
  { key: 'size', label: 'Serving Size', accessor: (r) => `${r.servingSize} ${r.servingUnit}` },
  { key: 'energy', label: 'Energy (kcal)', accessor: (r) => Math.round(r.energyKcal) },
  { key: 'protein', label: 'Protein (g)', accessor: (r) => Math.round(r.proteinG) },
]

export default function EditProductPage() {
  const params = useParams()
  const id = params.id as string
  const [form, setForm] = useState({
    name: '', brand: '', barcode: '', notes: '',
    nutritionalInfoSize: '', nutritionalInfoUnit: '',
    size: '', sizeUnit: '', numServings: '',
    energyKcal: '', proteinG: '', fatG: '', carbsG: '',
    saturatedFatG: '', sugarsG: '', fibreG: '', saltG: ''
  })
  const [servings, setServings] = useState<ServingRow[]>([])
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{ foodProduct: any }>(PRODUCT_QUERY, { id })
        if (res.foodProduct) {
          const p = res.foodProduct
          setForm({
            name: p.name, brand: p.brand || '', barcode: p.barcode || '', notes: p.notes,
            nutritionalInfoSize: String(p.nutritionalInfoSize), nutritionalInfoUnit: p.nutritionalInfoUnit,
            size: String(p.size), sizeUnit: p.sizeUnit, numServings: String(p.numServings),
            energyKcal: String(p.energyKcal), proteinG: String(p.proteinG), fatG: String(p.fatG), carbsG: String(p.carbsG),
            saturatedFatG: p.saturatedFatG ? String(p.saturatedFatG) : '', sugarsG: p.sugarsG ? String(p.sugarsG) : '',
            fibreG: p.fibreG ? String(p.fibreG) : '', saltG: p.saltG ? String(p.saltG) : ''
          })
          setServings(p.servings || [])
        }
      } catch (err) { console.error('Failed to fetch food product', err) }
      setLoading(false)
    }
    fetchData()
  }, [id])

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(UPDATE_MUTATION, {
        id, name: form.name, brand: form.brand || null, barcode: form.barcode || null, notes: form.notes,
        nutritionalInfoSize: parseFloat(form.nutritionalInfoSize), nutritionalInfoUnit: form.nutritionalInfoUnit,
        size: parseFloat(form.size), sizeUnit: form.sizeUnit, numServings: parseFloat(form.numServings),
        energyKcal: parseFloat(form.energyKcal), proteinG: parseFloat(form.proteinG), fatG: parseFloat(form.fatG), carbsG: parseFloat(form.carbsG),
        saturatedFatG: form.saturatedFatG ? parseFloat(form.saturatedFatG) : null,
        sugarsG: form.sugarsG ? parseFloat(form.sugarsG) : null,
        fibreG: form.fibreG ? parseFloat(form.fibreG) : null,
        saltG: form.saltG ? parseFloat(form.saltG) : null,
      })
    } finally { setSaving(false) }
  }

  const handleDelete = async () => { await graphqlRequest(DELETE_MUTATION, { id }) }

  if (loading) return <div className="p-12 text-center text-slate-500">Loading...</div>

  return (
    <div className="space-y-8">
      <EntityForm
        title="Edit Food Product"
        backHref="/products"
        onSave={handleSave}
        onDelete={handleDelete}
        saving={saving}
        fieldsets={[
          {
            title: 'General',
            content: (
              <>
                <FormField label="Brand" name="brand" value={form.brand} onChange={handleChange} />
                <FormField label="Name" name="name" value={form.name} onChange={handleChange} required />
                <FormField label="Barcode" name="barcode" value={form.barcode} onChange={handleChange} />
                <TextareaField label="Notes" name="notes" value={form.notes} onChange={handleChange} />
                <div className="grid grid-cols-2 gap-4 mt-4">
                  <FormField label="Size" name="size" type="number" step="0.1" value={form.size} onChange={handleChange} required />
                  <SelectField label="Size Unit" name="sizeUnit" value={form.sizeUnit} onChange={handleChange} options={UNIT_CHOICES} required />
                </div>
                <FormField label="Number of Servings (in size)" name="numServings" type="number" step="0.1" value={form.numServings} onChange={handleChange} required />
              </>
            ),
          },
          {
            title: 'Nutritional Info Base',
            content: (
              <div className="grid grid-cols-2 gap-4">
                <FormField label="Info Size Base" name="nutritionalInfoSize" type="number" step="0.1" value={form.nutritionalInfoSize} onChange={handleChange} required helpText="e.g. 100" />
                <SelectField label="Info Unit Base" name="nutritionalInfoUnit" value={form.nutritionalInfoUnit} onChange={handleChange} options={UNIT_CHOICES} required helpText="e.g. g" />
              </div>
            ),
          },
          {
            title: 'Main Nutrients (Per Info Base)',
            content: (
              <>
                <FormField label="Energy (kcal)" name="energyKcal" type="number" step="0.1" value={form.energyKcal} onChange={handleChange} required />
                <FormField label="Protein (g)" name="proteinG" type="number" step="0.1" value={form.proteinG} onChange={handleChange} required />
                <FormField label="Fat (g)" name="fatG" type="number" step="0.1" value={form.fatG} onChange={handleChange} required />
                <FormField label="Carbs (g)" name="carbsG" type="number" step="0.1" value={form.carbsG} onChange={handleChange} required />
              </>
            ),
          },
          {
            title: 'Extra Nutrients (Per Info Base)',
            content: (
              <>
                <FormField label="Saturated Fat (g)" name="saturatedFatG" type="number" step="0.1" value={form.saturatedFatG} onChange={handleChange} />
                <FormField label="Sugars (g)" name="sugarsG" type="number" step="0.1" value={form.sugarsG} onChange={handleChange} />
                <FormField label="Fibre (g)" name="fibreG" type="number" step="0.1" value={form.fibreG} onChange={handleChange} />
                <FormField label="Salt (g)" name="saltG" type="number" step="0.1" value={form.saltG} onChange={handleChange} />
              </>
            ),
          },
        ]}
      />

      <div>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold">Servings</h2>
        </div>
        <DataTable
          columns={servingColumns}
          data={servings}
          rowHref={(r) => `/servings/${r.id}?foodId=${id}`}
          addHref={`/servings/new?foodId=${id}`}
          addLabel="Add Serving"
          emptyMessage="No servings defined."
        />
      </div>
    </div>
  )
}
