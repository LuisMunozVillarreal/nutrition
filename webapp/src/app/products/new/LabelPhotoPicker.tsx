import { useEffect, useRef, useState } from 'react'
import { gql, graphqlRequest } from '@/lib/graphql'
import { labelPhoto } from './labelPhoto'

const EXTRACT = gql`
  mutation ExtractProductLabel($photos: [String!]!) {
    extractProductLabel(photos: $photos) { draftJson }
  }
`

export default function LabelPhotoPicker({ onReview, onCancel }: {
  onReview: (photos: string[], draft: Record<string, unknown>) => void
  onCancel: () => void
}) {
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const active = useRef(false)
  useEffect(() => {
    active.current = true
    return () => { active.current = false }
  }, [])

  async function extract() {
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
      onReview(photos, draft)
    } catch {
      // GraphQL errors can contain request variables, including the images.
      if (active.current) {
        setError('Could not read the labels. Retry or choose clearer photos.')
        setBusy(false)
      }
    }
  }

  return <section className="space-y-3">
    <p>Choose up to four clear label photos of one product. Read labels to fill the form, then review before saving. Your edits are kept.</p>
    <label className="block">Label photos
      <input type="file" className="block" accept="image/*" multiple disabled={busy} onChange={event => {
        const selected = Array.from(event.target.files!)
        event.target.value = ''
        if (files.length + selected.length > 4) {
          setError('Choose at most four photos of one product.')
          return
        }
        setError('')
        setFiles([...files, ...selected])
      }} />
    </label>
    <ul>{files.map((file, index) => <li key={index}>{file.name}{' '}
      <button type="button" className="underline" disabled={busy} onClick={() => setFiles(files.filter((_, i) => i !== index))}>Remove</button>
    </li>)}</ul>
    {error && <p role="alert">{error}</p>}
    <button type="button" className="btn btn-primary" disabled={busy || !files.length} onClick={extract}>{busy ? 'Reading labels…' : 'Read labels'}</button>{' '}
    <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel photos</button>
  </section>
}
