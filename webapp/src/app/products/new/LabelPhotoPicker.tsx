import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { gql, graphqlRequest } from '@/lib/graphql'
import { labelPhoto } from './labelPhoto'

const EXTRACT = gql`
  mutation ExtractProductLabel($photos: [String!]!) {
    extractProductLabel(photos: $photos) { draftJson }
  }
`

interface Batch {
  photos: string[]
  draft: Record<string, unknown>
}

export type MeasurementChoice = 'keep' | 'replace'

export default function LabelPhotoPicker({ onReview, onCancel }: {
  onReview: (photos: string[], draft: Record<string, unknown>, choice?: MeasurementChoice) => 'measurement-conflict' | 'barcode-conflict' | 'unit-conflict' | undefined
  onCancel: () => void
}) {
  const [files, setFiles] = useState<File[]>([])
  const [conflict, setConflict] = useState<Batch | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  // A read may finish after more edits. Review against the latest committed form.
  const latestReview = useRef(onReview)
  useLayoutEffect(() => { latestReview.current = onReview }, [onReview])
  const active = useRef(false)
  useEffect(() => {
    active.current = true
    return () => { active.current = false }
  }, [])

  function review(batch: Batch, choice?: MeasurementChoice) {
    const result = latestReview.current(batch.photos, batch.draft, choice)
    if (result === 'barcode-conflict') {
      setConflict(null)
      setError('The label barcode does not match your product barcode. No fields changed. Remove these photos and retry with the correct product.')
    } else if (result === 'unit-conflict') {
      setConflict(null)
      setError('The package unit and nutrition unit do not match. No fields changed. Check the units or retry with photos of the correct label.')
    } else if (result === 'measurement-conflict') {
      setConflict(batch)
    }
    setBusy(false)
  }

  async function extract() {
    setConflict(null)
    setBusy(true)
    setError('')
    try {
      const photos: string[] = []
      for (const file of files) {
        photos.push(await labelPhoto(file, files.length))
        if (!active.current) return
      }
      const result = await graphqlRequest<{ extractProductLabel: { draftJson: string } }>(EXTRACT, { photos })
      if (!active.current) return
      const draft = JSON.parse(result.extractProductLabel.draftJson)
      if (!draft || typeof draft !== 'object' || Array.isArray(draft)) throw new Error('Invalid draft')
      review({ photos, draft })
    } catch {
      // GraphQL errors can contain request variables, including the images.
      if (active.current) {
        setError('Could not read the labels. Retry or choose clearer photos. Use JPEG or PNG, at most 16 MiB, 24 megapixels and 8192 pixels per side.')
        setBusy(false)
      }
    }
  }

  return <section className="space-y-3">
    <p>Choose up to four clear label photos of one product. Selecting Read labels sends these photos to Google Gemini to extract product details. Review the result before saving.</p>
    <label className="block">Label photos
      <input type="file" className="block" accept="image/jpeg,image/png" multiple disabled={busy} onChange={event => {
        const selected = Array.from(event.target.files!)
        event.target.value = ''
        if (files.length + selected.length > 4) {
          setError('Choose at most four photos of one product.')
          return
        }
        setError('')
        setConflict(null)
        setFiles([...files, ...selected])
      }} />
    </label>
    <ul>{files.map((file, index) => <li key={index}>{file.name}{' '}
      <button type="button" className="underline" disabled={busy} onClick={() => { setConflict(null); setFiles(files.filter((_, i) => i !== index)) }}>Remove</button>
    </li>)}</ul>
    {conflict && <div>
      <p role="alert">Keep your current package size and unit, servings, nutrition basis, nutrient values and notes, or replace them all with the photo values. Missing photo values will be left blank.</p>
      <button type="button" className="btn btn-secondary" onClick={() => review(conflict, 'keep')}>Keep my measurements</button>
      <button type="button" className="btn btn-secondary" onClick={() => review(conflict, 'replace')}>Replace with photo measurements</button>
    </div>}
    {error && <p role="alert">{error}</p>}
    <button type="button" className="btn btn-primary" disabled={busy || !files.length} onClick={extract}>{busy ? 'Reading labels…' : 'Read labels'}</button>{' '}
    <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel photos</button>
  </section>
}
