'use client'

import { useRouter } from 'next/navigation'
import { ChevronUp, ChevronDown, Plus, Trash2 } from 'lucide-react'
import { useState, useMemo } from 'react'

export interface Column<T> {
  key: string
  label: string
  accessor: (row: T) => React.ReactNode
  sortable?: boolean
}

interface DataTableProps<T> {
  columns: Column<T>[]
  data: T[]
  rowHref?: (row: T) => string
  onDelete?: (row: T) => void
  addHref?: string
  addLabel?: string
  loading?: boolean
  emptyMessage?: string
}

export default function DataTable<T extends { id: string | number }>({
  columns,
  data,
  rowHref,
  onDelete,
  addHref,
  addLabel = 'Add New',
  loading = false,
  emptyMessage = 'No records found.',
}: DataTableProps<T>) {
  const router = useRouter()
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const sortedData = useMemo(() => {
    if (!sortKey) return data
    const col = columns.find(c => c.key === sortKey)
    if (!col) return data

    return [...data].sort((a, b) => {
      const aVal = col.accessor(a)
      const bVal = col.accessor(b)
      const aStr = String(aVal ?? '')
      const bStr = String(bVal ?? '')
      const cmp = aStr.localeCompare(bStr, undefined, { numeric: true })
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [data, sortKey, sortDir, columns])

  return (
    <div>
      {addHref && (
        <div className="page-header">
          <div />
          <button
            className="btn btn-primary"
            onClick={() => router.push(addHref)}
            data-testid="add-new-btn"
          >
            <Plus size={16} />
            {addLabel}
          </button>
        </div>
      )}

      <div className="glass-card rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-500">Loading...</div>
        ) : sortedData.length === 0 ? (
          <div className="p-12 text-center text-slate-500" data-testid="empty-table">
            {emptyMessage}
          </div>
        ) : (
          <table className="data-table" data-testid="data-table">
            <thead>
              <tr>
                {columns.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => col.sortable !== false && handleSort(col.key)}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.label}
                      {sortKey === col.key && (
                        sortDir === 'asc'
                          ? <ChevronUp size={12} />
                          : <ChevronDown size={12} />
                      )}
                    </span>
                  </th>
                ))}
                {onDelete && <th style={{ width: '1%' }}></th>}
              </tr>
            </thead>
            <tbody>
              {sortedData.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => rowHref && router.push(rowHref(row))}
                  data-testid={`table-row-${row.id}`}
                >
                  {columns.map((col) => (
                    <td key={col.key}>{col.accessor(row)}</td>
                  ))}
                  {onDelete && (
                    <td>
                      <button
                        className="btn btn-danger btn-sm"
                        onClick={(e) => {
                          e.stopPropagation()
                          onDelete(row)
                        }}
                        data-testid={`delete-btn-${row.id}`}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
