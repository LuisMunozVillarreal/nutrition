'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useRef, useState, ReactNode, FormEvent } from 'react'
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
  onSave: () => Promise<void | string>
  onDelete?: () => Promise<void>
  fieldsets: FieldsetConfig[]
  saving?: boolean
  disabled?: boolean
  children?: ReactNode
}

function errorMessage(error: unknown, fallback = 'An error occurred'): string {
  if (typeof error === 'string') return error
  if (typeof error === 'object' && error !== null) {
    const errorLike = error as { message?: unknown; stack?: unknown }
    if (typeof errorLike.stack === 'string' && errorLike.stack) return errorLike.stack
    if (typeof errorLike.message === 'string' && errorLike.message) return errorLike.message
  }
  return fallback
}

export default function EntityForm({
  title,
  backHref,
  onSave,
  onDelete,
  fieldsets,
  saving = false,
  disabled = false,
  children,
}: EntityFormProps) {
  const router = useRouter()
  const [hydrated, setHydrated] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const activeRef = useRef(false)

  useEffect(() => {
    activeRef.current = true
    setHydrated(true)
    return () => { activeRef.current = false }
  }, [])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    try {
      let destination: void | string
      try {
        destination = await onSave()
      } catch (saveErr: unknown) {
        throw new Error('API ERROR: ' + errorMessage(saveErr))
      }
      if (!activeRef.current) return
      try {
        router.push(destination ?? backHref)
      } catch (routeErr: unknown) {
        throw new Error('ROUTE ERROR: ' + errorMessage(routeErr))
      }
    } catch (err: unknown) {
      if (activeRef.current) setError(errorMessage(err))
    }
  }

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setError(null)
    try {
      await onDelete!()
      router.push(backHref)
    } catch (err: unknown) {
      setError(errorMessage(err))
      setConfirmDelete(false)
    }
  }

  if (!hydrated) {
    return (
      <div className="p-12 text-center text-slate-500" data-testid="form-hydrating">
        Loading form...
      </div>
    )
  }

  return (
    <form className="max-w-3xl mx-auto" data-testid="form-ready" onSubmit={handleSubmit}>
      {/* Header */}
      <div className="page-header">
        <div className="flex items-center gap-4">
          <button
            type="button"
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
              type="button"
              className="btn btn-danger"
              onClick={handleDelete}
              data-testid="delete-btn"
            >
              <Trash2 size={16} />
              {confirmDelete ? 'Confirm Delete' : 'Delete'}
            </button>
          )}
          <button
            type="submit"
            className="btn btn-primary"
            disabled={saving || disabled}
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
    </form>
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
