'use client'

import { Suspense, useRef, useState } from 'react'
import Image from 'next/image'
import LabelPhotoPicker, { type MeasurementChoice } from './LabelPhotoPicker'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { graphqlRequest, gql } from '@/lib/graphql'
import EntityForm from '@/components/EntityForm'
import { FormField, SelectField, TextareaField } from '@/components/FormField'
import { compatibleUnits, isCompatibleUnitPair, UNIT_CHOICES } from '@/lib/units'

const CREATE_MUTATION = gql`
  mutation CreateFoodProduct(
    $name: String!, $brand: String, $barcode: String, $notes: String!,
    $nutritionalInfoSize: Float!, $nutritionalInfoUnit: String!,
    $size: Float!, $sizeUnit: String!, $numServings: Float!,
    $energyKcal: Float!, $proteinG: Float!, $fatG: Float!, $carbsG: Float!,
    $saturatedFatG: Float, $sugarsG: Float, $fibreG: Float, $saltG: Float
  ) {
    createFoodProduct(
      name: $name, brand: $brand, barcode: $barcode, notes: $notes,
      nutritionalInfoSize: $nutritionalInfoSize, nutritionalInfoUnit: $nutritionalInfoUnit,
      size: $size, sizeUnit: $sizeUnit, numServings: $numServings,
      energyKcal: $energyKcal, proteinG: $proteinG, fatG: $fatG, carbsG: $carbsG,
      saturatedFatG: $saturatedFatG, sugarsG: $sugarsG, fibreG: $fibreG, saltG: $saltG
    ) { id }
  }
`

interface ProductFormState {
  name: string
  brand: string
  barcode: string
  notes: string
  nutritionalInfoSize: string
  nutritionalInfoUnit: string
  size: string
  sizeUnit: string
  numServings: string
  energyKcal: string
  proteinG: string
  fatG: string
  carbsG: string
  saturatedFatG: string
  sugarsG: string
  fibreG: string
  saltG: string
}

const DEFAULT_FORM: ProductFormState = {
  name: '', brand: '', barcode: '', notes: '',
  nutritionalInfoSize: '100', nutritionalInfoUnit: 'g',
  size: '100', sizeUnit: 'g', numServings: '1.0',
  energyKcal: '', proteinG: '', fatG: '', carbsG: '',
  saturatedFatG: '', sugarsG: '', fibreG: '', saltG: ''
}

// Fields the scan page can prefill through the query string.
const PREFILL_FIELDS: Array<keyof ProductFormState> = [
  'barcode', 'brand', 'name', 'size', 'sizeUnit', 'numServings',
  'nutritionalInfoSize', 'nutritionalInfoUnit', 'energyKcal', 'proteinG',
  'fatG', 'carbsG', 'saturatedFatG', 'sugarsG', 'fibreG', 'saltG'
]

const REQUIRED_MAIN_NUTRIENTS: Array<keyof ProductFormState> = [
  'energyKcal',
  'proteinG',
  'fatG',
  'carbsG',
]

const MEASUREMENT_FIELDS: Array<keyof ProductFormState> = [
  'size', 'sizeUnit', 'numServings', 'notes',
  'nutritionalInfoSize', 'nutritionalInfoUnit', ...REQUIRED_MAIN_NUTRIENTS,
  'saturatedFatG', 'sugarsG', 'fibreG', 'saltG',
]

const REQUIRED_LABEL_FIELDS = {
  name: 'Name', size: 'Package size', sizeUnit: 'Size unit', numServings: 'Number of servings',
  nutritionalInfoSize: 'Info size base', nutritionalInfoUnit: 'Info unit base',
  energyKcal: 'Energy', proteinG: 'Protein', fatG: 'Fat', carbsG: 'Carbs',
} as const

const BARCODE_CHECK = gql`
  query CheckLabelBarcode($barcode: String!) {
    foodProductByBarcode(barcode: $barcode, localOnly: true) { product { name } }
  }
`

interface ProductSearchParams {
  get(name: string): string | null
  toString(): string
}

// Match the catalog's GTIN lengths, GS1 check digit and UPC padding rules.
function normalizedGtin(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const digits = value.trim()
  if (!/^(?:[0-9]{8}|[0-9]{12,14})$/.test(digits)) return null
  let sum = 0
  for (let i = 1; i <= digits.length; i++) {
    sum += Number(digits[digits.length - i]) * (i % 2 ? 1 : 3)
  }
  return sum % 10 === 0 ? digits.replace(/^0{1,2}(?=\d{12,}$)/, '') : null
}

function initialForm(searchParams: ProductSearchParams): ProductFormState {
  const form = { ...DEFAULT_FORM }
  if (
    searchParams.get('fromBarcodeScan') === '1' &&
    searchParams.get('size') === null
  ) {
    form.size = ''
  }
  for (const field of PREFILL_FIELDS) {
    const value = searchParams.get(field)
    if (value !== null) form[field] = value
  }
  return form
}

function NewProductForm({ searchParams }: { searchParams: ProductSearchParams }) {
  const fromBarcodeScan = searchParams.get('fromBarcodeScan') === '1'
  const fromMealLog = fromBarcodeScan && searchParams.get('fromMealLog') === '1'
  const intakeDayId = fromBarcodeScan
    ? searchParams.get('intakeDayId')?.trim() || null
    : null
  const intakeDayDate = fromBarcodeScan && !intakeDayId
    ? searchParams.get('intakeDayDate')
    : null
  const [form, setForm] = useState(() => initialForm(searchParams))
  const [saving, setSaving] = useState(false)

  const [picking, setPicking] = useState(searchParams.get('labelPhotos') === '1')
  const [photos, setPhotos] = useState<string[]>([])
  const edited = useRef(new Set<string>())
  const reviewing = photos.length > 0
  const nutrientStep = reviewing ? '0.01' : '0.1'
  const missing = Object.entries(REQUIRED_LABEL_FIELDS)
    .filter(([key]) => !form[key as keyof ProductFormState].trim())
    .map(([, label]) => label)

  function review(nextPhotos: string[], draft: Record<string, unknown>, choice?: MeasurementChoice) {
    const retained = (key: keyof ProductFormState) => edited.current.has(key) || searchParams.get(key) !== null
    const extracted = normalizedGtin(draft.barcode)
    const retainedBarcodes = [searchParams.get('barcode'), retained('barcode') ? form.barcode : null]
    if (extracted && retainedBarcodes.map(normalizedGtin).some(code => code && code !== extracted)) {
      return 'barcode-conflict'
    }
    if (!choice && MEASUREMENT_FIELDS.some(retained)) {
      return 'measurement-conflict'
    }
    const next = { ...form }
    for (const key of Object.keys(next) as Array<keyof ProductFormState>) {
      if (MEASUREMENT_FIELDS.includes(key) ? choice === 'keep' : retained(key)) continue
      const value = draft[key]
      next[key] = typeof value === 'string' || typeof value === 'number' ? String(value) : ''
    }
    if (next.sizeUnit && next.nutritionalInfoUnit && !isCompatibleUnitPair(next.sizeUnit, next.nutritionalInfoUnit)) {
      return 'unit-conflict'
    }
    setForm(next)
    setPhotos(nextPhotos)
    setPicking(false)
  }

  const handleChange = (name: string, value: string) => {
    edited.current.add(name)
    setForm(prev => {
      if (name === 'sizeUnit' && !isCompatibleUnitPair(value, prev.nutritionalInfoUnit)) {
        return { ...prev, sizeUnit: value, nutritionalInfoUnit: reviewing ? '' : value }
      }
      return { ...prev, [name]: value }
    })
  }

  const handleSave = async () => {
    if (picking) throw new Error('Finish reading labels or cancel photos before saving.')
    if (reviewing && missing.length) throw new Error(`Complete required fields: ${missing.join(', ')}`)
    const size = Number(form.size)
    if (!form.size.trim() || !Number.isFinite(size) || size <= 0) {
      throw new Error('Enter a valid package size before saving')
    }
    if (REQUIRED_MAIN_NUTRIENTS.some((field) => !form[field].trim())) {
      throw new Error('Enter all required main nutrients before saving')
    }
    setSaving(true)
    try {
      if (reviewing && form.barcode.trim()) {
        const { foodProductByBarcode } = await graphqlRequest<{ foodProductByBarcode: { product: { name: string } | null } }>(BARCODE_CHECK, { barcode: form.barcode.trim() })
        if (foodProductByBarcode.product) throw new Error(`This barcode already belongs to ${foodProductByBarcode.product.name}. No product was created.`)
      }
      const result = await graphqlRequest<{ createFoodProduct: { id: string } }>(CREATE_MUTATION, {
        name: form.name,
        brand: form.brand || null,
        barcode: form.barcode || null,
        notes: form.notes,
        nutritionalInfoSize: parseFloat(form.nutritionalInfoSize),
        nutritionalInfoUnit: form.nutritionalInfoUnit,
        size,
        sizeUnit: form.sizeUnit,
        numServings: parseFloat(form.numServings),
        energyKcal: parseFloat(form.energyKcal),
        proteinG: parseFloat(form.proteinG),
        fatG: parseFloat(form.fatG),
        carbsG: parseFloat(form.carbsG),
        saturatedFatG: form.saturatedFatG ? parseFloat(form.saturatedFatG) : null,
        sugarsG: form.sugarsG ? parseFloat(form.sugarsG) : null,
        fibreG: form.fibreG ? parseFloat(form.fibreG) : null,
        saltG: form.saltG ? parseFloat(form.saltG) : null,
      })
      if (fromMealLog || intakeDayId || intakeDayDate !== null) {
        const params = new URLSearchParams()
        if (intakeDayId) params.set('dayId', intakeDayId)
        else if (intakeDayDate !== null) params.set('dayDate', intakeDayDate)
        params.set('productId', result.createFoodProduct.id)
        // Intake quantity is separate from the product's package numServings.
        for (const field of ['intakeMeal', 'intakeNumServings']) {
          const value = searchParams.get(field)
          if (value !== null) params.set(field, value)
        }
        return `/intakes/new?${params.toString()}`
      }
    } finally { setSaving(false) }
  }

  return (
    <div className={reviewing ? 'grid gap-6 lg:grid-cols-[minmax(16rem,1fr)_2fr]' : ''}>
      {reviewing && <aside aria-label="Source label photos" className="space-y-3">
        <h2 className="font-semibold">Source label photos</h2>
        {photos.map((src, index) => <Image key={index} unoptimized src={src} width={1000} height={1000}
          className="w-full h-auto" alt={`Label photo ${index + 1}`} />)}
      </aside>}
    <EntityForm
      title="New Food Product"
      backHref="/products"
      onSave={handleSave}
      saving={saving}
      disabled={picking}
      fieldsets={[
        {
          title: 'General',
          content: (
            <>
              <div className="md:col-span-2">
                <Link
                  href="/scan?mode=product"
                  className="btn btn-secondary inline-flex"
                >
                  Scan Product
                </Link>{' '}
                {picking ? <LabelPhotoPicker onReview={review} onCancel={() => setPicking(false)} /> : (
                  <button type="button" className="btn btn-secondary" disabled={saving} onClick={() => setPicking(true)}>
                    {reviewing ? 'Read new photos' : 'Create from label photos'}
                  </button>
                )}
                {reviewing && <p role="status" className="mt-3">{missing.length
                  ? `Complete required fields: ${missing.join(', ')}.`
                  : 'Check these values against the labels, then select Save.'}</p>}
              </div>
              <FormField label="Brand" name="brand" value={form.brand} onChange={handleChange} />
              <FormField label="Name" name="name" value={form.name} onChange={handleChange} required />
              <FormField label="Barcode" name="barcode" value={form.barcode} onChange={handleChange} />
              <TextareaField label="Notes" name="notes" value={form.notes} onChange={handleChange} />

              <div className="grid grid-cols-2 gap-4 mt-4">
                <FormField label="Size" name="size" type="number" step="0.1" min="0.1" value={form.size} onChange={handleChange} required />
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
              <SelectField label="Info Unit Base" name="nutritionalInfoUnit" value={form.nutritionalInfoUnit} onChange={handleChange} options={reviewing && !form.sizeUnit ? UNIT_CHOICES : compatibleUnits(form.sizeUnit)} required helpText="e.g. g" />
            </div>
          ),
        },
        {
          title: 'Main Nutrients (Per Info Base)',
          content: (
            <>
              <FormField label="Energy (kcal)" name="energyKcal" type="number" step={nutrientStep} min="0" value={form.energyKcal} onChange={handleChange} required />
              <FormField label="Protein (g)" name="proteinG" type="number" step={nutrientStep} min="0" value={form.proteinG} onChange={handleChange} required />
              <FormField label="Fat (g)" name="fatG" type="number" step={nutrientStep} min="0" value={form.fatG} onChange={handleChange} required />
              <FormField label="Carbs (g)" name="carbsG" type="number" step={nutrientStep} min="0" value={form.carbsG} onChange={handleChange} required />
            </>
          ),
        },
        {
          title: 'Extra Nutrients (Per Info Base)',
          content: (
            <>
              <FormField label="Saturated Fat (g)" name="saturatedFatG" type="number" step={nutrientStep} min="0" value={form.saturatedFatG} onChange={handleChange} />
              <FormField label="Sugars (g)" name="sugarsG" type="number" step={nutrientStep} min="0" value={form.sugarsG} onChange={handleChange} />
              <FormField label="Fibre (g)" name="fibreG" type="number" step={nutrientStep} min="0" value={form.fibreG} onChange={handleChange} />
              <FormField label="Salt (g)" name="saltG" type="number" step={nutrientStep} min="0" value={form.saltG} onChange={handleChange} />
            </>
          ),
        },
      ]}
    />
    </div>
  )
}

function RoutedNewProductForm() {
  const searchParams = useSearchParams()
  return (
    <NewProductForm
      key={searchParams.toString()}
      searchParams={searchParams}
    />
  )
}

export default function NewProductPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-slate-500">Loading form...</div>}>
      <RoutedNewProductForm />
    </Suspense>
  )
}
