'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { graphqlRequest, gql } from '../../../lib/graphql'
import EntityForm from '../../../components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '../../../components/FormField'
import DataTable, { Column } from '../../../components/DataTable'

const RECIPE_QUERY = gql`
  query GetRecipe($id: ID!) {
    recipe(id: $id) {
      id brand name description
      size sizeUnit numServings
      energyKcal proteinG fatG carbsG
      saturatedFatG sugarsG fibreG saltG
      ingredients {
        id foodId foodLabel numServings
        energyKcal proteinG fatG carbsG
      }
    }
  }
`

const UPDATE_MUTATION = gql`
  mutation UpdateRecipe(
    $id: ID!, $name: String!, $brand: String, $description: String!,
    $size: Float!, $sizeUnit: String!, $numServings: Float!,
    $energyKcal: Float!, $proteinG: Float!, $fatG: Float!, $carbsG: Float!,
    $saturatedFatG: Float, $sugarsG: Float, $fibreG: Float, $saltG: Float
  ) {
    updateRecipe(
      id: $id, name: $name, brand: $brand, description: $description,
      size: $size, sizeUnit: $sizeUnit, numServings: $numServings,
      energyKcal: $energyKcal, proteinG: $proteinG, fatG: $fatG, carbsG: $carbsG,
      saturatedFatG: $saturatedFatG, sugarsG: $sugarsG, fibreG: $fibreG, saltG: $saltG
    ) { id }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteRecipe($id: ID!) {
    deleteRecipe(id: $id)
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

interface IngredientRow {
  id: string
  foodLabel: string
  numServings: number
  energyKcal: number
  proteinG: number
  fatG: number
  carbsG: number
}

const ingredientColumns: Column<IngredientRow>[] = [
  { key: 'food', label: 'Ingredient', accessor: (r) => r.foodLabel },
  { key: 'servings', label: 'Servings', accessor: (r) => r.numServings },
  { key: 'energy', label: 'Energy (kcal)', accessor: (r) => Math.round(r.energyKcal) },
  { key: 'protein', label: 'Protein (g)', accessor: (r) => Math.round(r.proteinG) },
  { key: 'fat', label: 'Fat (g)', accessor: (r) => Math.round(r.fatG) },
  { key: 'carbs', label: 'Carbs (g)', accessor: (r) => Math.round(r.carbsG) },
]

export default function EditRecipePage() {
  const params = useParams()
  const id = params.id as string
  const [form, setForm] = useState({
    name: '', brand: '', description: '',
    size: '', sizeUnit: '', numServings: '',
    energyKcal: '', proteinG: '', fatG: '', carbsG: '',
    saturatedFatG: '', sugarsG: '', fibreG: '', saltG: ''
  })
  const [ingredients, setIngredients] = useState<IngredientRow[]>([])
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{ recipe: any }>(RECIPE_QUERY, { id })
        if (res.recipe) {
          const r = res.recipe
          setForm({
            name: r.name, brand: r.brand || '', description: r.description || '',
            size: String(r.size), sizeUnit: r.sizeUnit, numServings: String(r.numServings),
            energyKcal: String(r.energyKcal), proteinG: String(r.proteinG), fatG: String(r.fatG), carbsG: String(r.carbsG),
            saturatedFatG: r.saturatedFatG ? String(r.saturatedFatG) : '',
            sugarsG: r.sugarsG ? String(r.sugarsG) : '',
            fibreG: r.fibreG ? String(r.fibreG) : '',
            saltG: r.saltG ? String(r.saltG) : ''
          })
          setIngredients(r.ingredients || [])
        }
      } catch (err) { console.error('Failed to fetch recipe', err) }
      setLoading(false)
    }
    fetchData()
  }, [id])

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(UPDATE_MUTATION, {
        id, name: form.name, brand: form.brand || null, description: form.description,
        size: parseFloat(form.size), sizeUnit: form.sizeUnit, numServings: parseFloat(form.numServings),
        energyKcal: parseFloat(form.energyKcal), proteinG: parseFloat(form.proteinG),
        fatG: parseFloat(form.fatG), carbsG: parseFloat(form.carbsG),
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
        title="Edit Recipe"
        backHref="/recipes"
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
                <TextareaField label="Description" name="description" value={form.description} onChange={handleChange} />
                <div className="grid grid-cols-2 gap-4 mt-4">
                  <FormField label="Size" name="size" type="number" step="0.1" value={form.size} onChange={handleChange} required />
                  <SelectField label="Size Unit" name="sizeUnit" value={form.sizeUnit} onChange={handleChange} options={UNIT_CHOICES} required />
                </div>
                <FormField label="Number of Servings" name="numServings" type="number" step="0.1" value={form.numServings} onChange={handleChange} required />
              </>
            ),
          },
          {
            title: 'Main Nutrients',
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
            title: 'Extra Nutrients',
            collapsible: true,
            defaultCollapsed: true,
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
          <h2 className="text-xl font-bold">Ingredients</h2>
        </div>
        <DataTable
          columns={ingredientColumns}
          data={ingredients}
          emptyMessage="No ingredients added yet."
        />
      </div>
    </div>
  )
}
