'use client'

import { Suspense, useState } from 'react'
import { useSession } from 'next-auth/react'
import { useSearchParams } from 'next/navigation'
import { consentRedirect, parseAuthorization } from '@/lib/healthAuthorization'

function Consent() {
  const query = useSearchParams()
  const { data: session } = useSession()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  let request
  try {
    request = parseAuthorization(new URLSearchParams(query.toString()), window.location.origin)
  } catch {
    return <p role="alert">Invalid sign-in request. Return to the Android app and start again.</p>
  }
  const authorization = request
  async function connect() {
    setBusy(true)
    setError(false)
    try {
      const redirect = await consentRedirect(authorization, session?.accessToken)
      window.location.assign(redirect)
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }
  const cancel = `${authorization.redirect_uri}?${new URLSearchParams({
    error: 'access_denied', state: authorization.state, issuer: authorization.issuer,
  })}`
  return (
    <section className="glass-card mx-auto max-w-lg rounded-xl p-6">
      <h1 className="text-xl font-semibold">Connect Nutrition for Android</h1>
      <p className="mt-4">Signed in as {session?.user?.email}.</p>
      <p className="mt-2">Allow {authorization.device_name} to upload daily step totals to this Nutrition account?</p>
      <p className="mt-2 text-sm text-slate-400">The app cannot access your password. It stays signed in for background sync until you disconnect it or its renewable credential expires after 180 days without renewal. Manage access in Devices.</p>
      <button className="btn btn-primary mt-6" type="button" disabled={busy} onClick={() => void connect()}>
        {busy ? 'Connecting…' : 'Connect phone'}
      </button>
      {!busy && <a className="btn ml-3" href={cancel}>Cancel</a>}
      {error && <p role="alert" className="mt-4">Could not connect this phone. Retry or cancel and sign in again.</p>}
    </section>
  )
}

export default function AuthorizePage() {
  return <Suspense fallback={<p>Loading sign-in…</p>}><Consent /></Suspense>
}
