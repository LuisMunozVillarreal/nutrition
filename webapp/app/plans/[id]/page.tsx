'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { graphqlRequest, gql } from '@/app/lib/graphql'
import EntityForm from '@/app/components/EntityForm'
import { FormField, SelectField, TextareaField, CheckboxField, ReadonlyField } from '@/app/components/FormField'
import DataTable, { Column } from '@/app/components/DataTable'

const PLAN_QUERY = gql`
  query GetWeekPlan($id: ID!) {
    weekPlan(id: $id) {
      id startDate proteinGKg fatPerc deficit completed twee
      energyKcalGoal energyKcal
      days {
        id day dayNum completed energyKcalGoal energyKcal
      }
    }
  }
`

const UPDATE_MUTATION = gql`
  mutation UpdateWeekPlan($id: ID!, $proteinGKg: Float!, $fatPerc: Float!, $deficit: Int!) {
    updateWeekPlan(id: $id, proteinGKg: $proteinGKg, fatPerc: $fatPerc, deficit: $deficit) { id }
  }
`

const DELETE_MUTATION = gql`
  mutation DeleteWeekPlan($id: ID!) {
    deleteWeekPlan(id: $id)
  }
`

interface DayRow {
  id: string
  day: string
  dayNum: number
  completed: boolean
  energyKcalGoal: number
  energyKcal: number
}

const dayColumns: Column<DayRow>[] = [
  { key: 'dayNum', label: 'Day #', accessor: (r) => r.dayNum },
  { key: 'day', label: 'Date', accessor: (r) => r.day },
  { key: 'completed', label: 'Done', accessor: (r) => r.completed ? 'Yes' : 'No' },
  { key: 'energy', label: 'Energy', accessor: (r) => `${Math.round(r.energyKcal)} / ${Math.round(r.energyKcalGoal)} kcal` },
]

export default function EditPlanPage() {
  const params = useParams()
  const id = params.id as string
  const [form, setForm] = useState({ proteinGKg: '', fatPerc: '', deficit: '' })
  const [readOnly, setReadOnly] = useState<any>({})
  const [days, setDays] = useState<DayRow[]>([])
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{ weekPlan: any }>(PLAN_QUERY, { id })
        if (res.weekPlan) {
          setForm({
            proteinGKg: String(res.weekPlan.proteinGKg),
            fatPerc: String(res.weekPlan.fatPerc),
            deficit: String(res.weekPlan.deficit),
          })
          setReadOnly({
            startDate: res.weekPlan.startDate,
            completed: res.weekPlan.completed ? 'Yes' : 'No',
            twee: Math.round(res.weekPlan.twee),
            energyKcalGoal: Math.round(res.weekPlan.energyKcalGoal),
            energyKcal: Math.round(res.weekPlan.energyKcal),
          })
          setDays(res.weekPlan.days || [])
        }
      } catch (err) { console.error('Failed to fetch plan', err) }
      setLoading(false)
    }
    fetchData()
  }, [id])

  const handleChange = (name: string, value: string) => { setForm(prev => ({ ...prev, [name]: value })) }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(UPDATE_MUTATION, {
        id, proteinGKg: parseFloat(form.proteinGKg),
        fatPerc: parseFloat(form.fatPerc), deficit: parseInt(form.deficit),
      })
    } finally { setSaving(false) }
  }

  const handleDelete = async () => { await graphqlRequest(DELETE_MUTATION, { id }) }

  if (loading) return <div className="p-12 text-center text-slate-500">Loading...</div>

  return (
    <div className="space-y-8">
      <EntityForm
        title="Edit Week Plan"
        backHref="/plans"
        onSave={handleSave}
        onDelete={handleDelete}
        saving={saving}
        fieldsets={[
          {
            title: 'Goal Configuration',
            content: (
              <>
                <FormField label="Protein (g/kg)" name="proteinGKg" type="number" step="0.1" value={form.proteinGKg} onChange={handleChange} required />
                <FormField label="Fat (%)" name="fatPerc" type="number" step="0.1" value={form.fatPerc} onChange={handleChange} required />
                <FormField label="Deficit (kcals)" name="deficit" type="number" value={form.deficit} onChange={handleChange} required />
              </>
            ),
          },
          {
            title: 'Status & Progress',
            content: (
              <>
                <ReadonlyField label="Start Date" value={readOnly.startDate} />
                <ReadonlyField label="Completed" value={readOnly.completed} />
                <ReadonlyField label="TWEE" value={readOnly.twee} />
                <ReadonlyField label="Energy Goal" value={readOnly.energyKcalGoal} />
                <ReadonlyField label="Energy Intake" value={readOnly.energyKcal} />
              </>
            ),
          },
        ]}
      />

      <div>
        <h2 className="text-xl font-bold mb-4">Days in this Plan</h2>
        <DataTable
          columns={dayColumns}
          data={days}
          rowHref={(r) => `/days/${r.id}`}
        />
      </div>
    </div>
  )
}
