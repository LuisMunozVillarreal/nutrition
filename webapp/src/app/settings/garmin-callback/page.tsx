'use client'

import { Suspense, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { graphqlRequest, gql } from '@/lib/graphql'
import { garminProviderErrorMessage } from '@/lib/garminCallback'
import { consumeGarminCallbackHandoff } from '@/lib/garminCallbackHandoff'

const COMPLETE_GARMIN_AUTHORIZATION_MUTATION = gql`
  mutation CompleteGarminAuthorization($code: String!, $state: String!) {
    completeGarminAuthorization(code: $code, state: $state) {
      enabled
      connected
      hasRefreshToken
      lastSyncedAt
      lastSyncSummary {
        imported
        duplicates
        unsupported
        invalid
      }
    }
  }
`

const CANCEL_GARMIN_AUTHORIZATION_MUTATION = gql`
  mutation CancelGarminAuthorization($state: String!) {
    cancelGarminAuthorization(state: $state)
  }
`

function ErrorPanel({ message }: { message: string }) {
  const router = useRouter()

  return (
    <main className="max-w-3xl mx-auto p-6 md:p-10">
      <div className="glass-card p-6 rounded-2xl space-y-4">
        <h1 className="text-2xl font-black text-white">Garmin Connection Error</h1>
        <p
          className="text-slate-200"
          role="alert"
          aria-live="assertive"
          data-testid="garmin-callback-error"
        >
          {message}
        </p>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => router.replace('/settings')}
          data-testid="garmin-callback-return"
        >
          Return to settings
        </button>
      </div>
    </main>
  )
}

function GarminCallbackFlow() {
  const router = useRouter()
  const [message, setMessage] = useState('Completing Garmin setup...')
  const [error, setError] = useState<string | null>(null)
  const [isDone, setIsDone] = useState(false)
  const hasStarted = useRef(false)

  useEffect(() => {
    if (hasStarted.current) return
    hasStarted.current = true

    const parsed = consumeGarminCallbackHandoff(window.sessionStorage)

    if (parsed.kind === 'providerError') {
      void (async () => {
        await graphqlRequest(CANCEL_GARMIN_AUTHORIZATION_MUTATION, {
          state: parsed.state,
        }).catch(() => undefined)
        setError(garminProviderErrorMessage(parsed.error))
      })()
      return
    }

    if (parsed.kind === 'invalid') {
      void (async () => {
        setError(parsed.message)
      })()
      return
    }

    void (async () => {
      try {
        await graphqlRequest(COMPLETE_GARMIN_AUTHORIZATION_MUTATION, {
          code: parsed.code,
          state: parsed.state,
        })
        setMessage('Garmin connected. Returning to settings...')
        setIsDone(true)
        router.replace('/settings')
      } catch {
        setError('Garmin connection failed during completion.')
      }
    })()
  }, [router])

  if (error) {
    return <ErrorPanel message={error} />
  }

  return (
    <main className="max-w-3xl mx-auto p-6 md:p-10">
        <section className="glass-card p-6 rounded-2xl">
        {isDone ? (
          <p
            className="text-green-300"
            role="status"
            aria-live="polite"
            data-testid="garmin-callback-success"
          >
            {message}
          </p>
        ) : (
          <p role="status" aria-live="polite" data-testid="garmin-callback-loading">
            {message}
          </p>
        )}
      </section>
    </main>
  )
}

export default function GarminCallbackPage() {
  return (
    <Suspense fallback={<div className="p-12 text-center text-slate-500" data-testid="garmin-callback-loading">Preparing Garmin callback...</div>}>
      <GarminCallbackFlow />
    </Suspense>
  )
}
