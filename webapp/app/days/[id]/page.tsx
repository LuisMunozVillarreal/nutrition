'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { graphqlRequest, gql } from '../../../lib/graphql'
import EntityForm from '../../components/EntityForm'
import { FormField, ReadonlyField, CheckboxField } from '../../components/FormField'
import DataTable, { Column } from '../../components/DataTable'

const DAY_QUERY = gql`
  query GetDay($id: ID!) {
    day(id: $id) {
      id planId day dayNum deficit tracked completed
      energyKcalGoal proteinGGoal fatGGoal carbsGGoal
      energyKcal proteinG fatG carbsG tdee
      intakes {
        id meal mealOrder numServings energyKcal proteinG fatG carbsG
      }
    }
  }
`

const UPDATE_MUTATION = gql`
  mutation UpdateDay($id: ID!, $tracked: Boolean!) {
    updateDay(id: $id, tracked: $tracked) { id tracked }
  }
`

interface IntakeRow {
  id: string
  meal: string
  numServings: number
  energyKcal: number
  proteinG: number
}

const intakeColumns: Column<IntakeRow>[] = [
  { key: 'meal', label: 'Meal', accessor: (r) => r.meal.charAt(0).toUpperCase() + r.meal.slice(1) },
  { key: 'servings', label: 'Servings', accessor: (r) => r.numServings },
  { key: 'energy', label: 'Energy (kcal)', accessor: (r) => Math.round(r.energyKcal) },
  { key: 'protein', label: 'Protein (g)', accessor: (r) => Math.round(r.proteinG) },
]

export default function EditDayPage() {
  const params = useParams()
  const id = params.id as string
  const [form, setForm] = useState({ tracked: false })
  const [readOnly, setReadOnly] = useState<any>({})
  const [intakes, setIntakes] = useState<IntakeRow[]>([])
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await graphqlRequest<{ day: any }>(DAY_QUERY, { id })
        if (res.day) {
          setForm({ tracked: res.day.tracked })
          setReadOnly(res.day)
          setIntakes(res.day.intakes || [])
        }
      } catch (err) { console.error('Failed to fetch day', err) }
      setLoading(false)
    }
    fetchData()
  }, [id])

  const handleCheckboxChange = (name: string, checked: boolean) => {
    setForm(prev => ({ ...prev, [name]: checked }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await graphqlRequest(UPDATE_MUTATION, { id, tracked: form.tracked })
    } finally { setSaving(false) }
  }

  if (loading) return <div className="p-12 text-center text-slate-500">Loading...</div>

  return (
    <div className="space-y-8">
      <EntityForm
        title={`Day ${readOnly.dayNum} - ${readOnly.day}`}
        backHref={`/plans/${readOnly.planId}`}
        onSave={handleSave}
        saving={saving}
        fieldsets={[
          {
            title: 'Settings',
            content: (
              <CheckboxField label="Tracked" name="tracked" checked={form.tracked} onChange={handleCheckboxChange} helpText="Uncheck to estimate goals using formulas." />
            ),
          },
          {
            title: 'Macros & Progress',
            content: (
              <>
                <ReadonlyField label="Energy (kcal)" value={`${Math.round(readOnly.energyKcal)} / ${Math.round(readOnly.energyKcalGoal)}`} />
                <ReadonlyField label="Protein (g)" value={`${Math.round(readOnly.proteinG)} / ${Math.round(readOnly.proteinGGoal)}`} />
                <ReadonlyField label="Fat (g)" value={`${Math.round(readOnly.fatG)} / ${Math.round(readOnly.fatGGoal)}`} />
                <ReadonlyField label="Carbs (g)" value={`${Math.round(readOnly.carbsG)} / ${Math.round(readOnly.carbsGGoal)}`} />
                <ReadonlyField label="TDEE" value={Math.round(readOnly.tdee)} />
                <ReadonlyField label="Completed" value={readOnly.completed ? 'Yes' : 'No'} />
              </>
            ),
          },
        ]}
      />

      <div>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-bold">Intakes</h2>
        </div>
        <DataTable
          columns={intakeColumns}
          data={intakes}
          rowHref={(r) => `/intakes/${r.id}`}
          addHref="/intakes/new"
          addLabel="Log Intake"
          emptyMessage="No intakes logged for this day."
        />
      </div>
    </div>
  )
}
