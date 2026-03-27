'use client'

import { useRouter } from 'next/navigation'
import { useState, ReactNode } from 'react'
import { Save, ArrowLeft, Trash2, ChevronDown, ChevronRight } from 'lucide-react'

interface FieldsetConfig {
  title: string
  collapsible?: boolean
  defaultCollapsed?: boolean
  content: ReactNode
}

interface EntityFormProps {
  title: string
  backHref: string
  onSave: () => Promise<void>
  onDelete?: () => Promise<void>
  fieldsets: FieldsetConfig[]
  saving?: boolean
  children?: ReactNode
}

export default function EntityForm({
  title,
  backHref,
  onSave,
  onDelete,
  fieldsets,
  saving = false,
  children,
}: EntityFormProps) {
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const handleSave = async () => {
    setError(null)
    try {
      try {
        await onSave()
      } catch (saveErr: any) {
        throw new Error('API ERROR: ' + (saveErr?.stack || saveErr?.message))
      }
      try {
        router.push(backHref)
      } catch (routeErr: any) {
        throw new Error('ROUTE ERROR: ' + (routeErr?.stack || routeErr?.message))
      }
    } catch (err: any) {
      setError(err?.stack || err?.message || 'An error occurred')
    }
  }

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    if (onDelete) {
      setError(null)
      try {
        await onDelete()
        router.push(backHref)
      } catch (err: any) {
        setError(err?.stack || err?.message || 'An error occurred')
        setConfirmDelete(false)
      }
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      {/* Header */}
      <div className="page-header">
        <div className="flex items-center gap-4">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => router.push(backHref)}
            data-testid="back-btn"
          >
            <ArrowLeft size={16} />
          </button>
          <h1 className="page-title">{title}</h1>
        </div>
        <div className="flex items-center gap-2">
          {onDelete && (
            <button
              className="btn btn-danger"
              onClick={handleDelete}
              data-testid="delete-btn"
            >
              <Trash2 size={16} />
              {confirmDelete ? 'Confirm Delete' : 'Delete'}
            </button>
          )}
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={saving}
            data-testid="save-btn"
          >
            <Save size={16} />
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      {error && (
        <div className="toast toast-error mb-4 static" data-testid="form-error">
          {error}
        </div>
      )}

      {/* Fieldsets */}
      {fieldsets.map((fs) => (
        <Fieldset
          key={fs.title}
          title={fs.title}
          collapsible={fs.collapsible}
          defaultCollapsed={fs.defaultCollapsed}
        >
          {fs.content}
        </Fieldset>
      ))}

      {children}
    </div>
  )
}

function Fieldset({
  title,
  collapsible = false,
  defaultCollapsed = false,
  children,
}: {
  title: string
  collapsible?: boolean
  defaultCollapsed?: boolean
  children: ReactNode
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)

  return (
    <fieldset className={`fieldset ${collapsed ? 'collapsed' : ''}`}>
      <legend
        className="fieldset-legend"
        onClick={() => collapsible && setCollapsed(!collapsed)}
      >
        {collapsible && (
          collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />
        )}
        {title}
      </legend>
      <div className="fieldset-content mt-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {children}
        </div>
      </div>
    </fieldset>
  )
}
