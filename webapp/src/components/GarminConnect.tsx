'use client'

import { useCallback, useRef, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'

const BEGIN_GARMIN_AUTHORIZATION_MUTATION = gql`
  mutation BeginGarminAuthorization {
    beginGarminAuthorization {
      authorizationUrl
      state
      expiresAt
    }
  }
`

const DISCONNECT_GARMIN_MUTATION = gql`
  mutation DisconnectGarmin {
    disconnectGarmin
  }
`

interface GarminSyncSummary {
  imported: number
  duplicates: number
  unsupported: number
  invalid: number
}

export interface GarminStatus {
  enabled: boolean
  connected: boolean
  hasRefreshToken: boolean
  lastSyncedAt: string | null
  lastSyncSummary: GarminSyncSummary | null
}

interface GarminAuthStart {
  authorizationUrl: string
  state: string
  expiresAt: string
}

interface GarminConnectProps {
  status: GarminStatus | null
  loading: boolean
  requestError: string | null
  onStatusRefresh: () => void
}

function resolveError(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'Garmin request failed. Please try again.'
}

export default function GarminConnect({
  status,
  loading,
  requestError,
  onStatusRefresh,
}: GarminConnectProps) {
  const [actionError, setActionError] = useState<string | null>(null)
  const [requestInFlight, setRequestInFlight] = useState(false)
  const statusRef = useRef<HTMLParagraphElement | null>(null)

  const clearMessages = useCallback(() => {
    setActionError(null)
  }, [])

  const handleConnect = async () => {
    if (!status?.enabled) return
    clearMessages()
    setRequestInFlight(true)

    try {
      const response = await graphqlRequest<{
        beginGarminAuthorization: GarminAuthStart
      }>(BEGIN_GARMIN_AUTHORIZATION_MUTATION)

      if (typeof window !== 'undefined') {
        window.location.assign(response.beginGarminAuthorization.authorizationUrl)
      }
    } catch (error) {
      setActionError(resolveError(error))
    } finally {
      setRequestInFlight(false)
    }
  }

  const handleDisconnect = async () => {
    clearMessages()

    if (!status?.connected && !status?.hasRefreshToken) return

    const confirmed = window.confirm('Disconnect Garmin integration?')
    if (!confirmed) {
      return
    }

    try {
      setRequestInFlight(true)
      const response = await graphqlRequest<{ disconnectGarmin: boolean }>(
        DISCONNECT_GARMIN_MUTATION,
      )
      if (!response.disconnectGarmin) {
        setActionError('Garmin was already disconnected.')
        return
      }

      onStatusRefresh()
    } catch (error) {
      setActionError(resolveError(error))
    } finally {
      setRequestInFlight(false)
    }
  }

  if (loading) {
    return (
      <div
        className="glass-card p-6 rounded-2xl"
        data-testid="garmin-loading"
        role="status"
        aria-live="polite"
      >
        Loading Garmin status...
      </div>
    )
  }

  const canConnect =
    status?.enabled && !status.connected && !status.hasRefreshToken
  const canDisconnect = status?.connected || status?.hasRefreshToken

  const statusText = !status
    ? 'Unknown'
    : status.connected
      ? 'Connected'
      : status.enabled
        ? 'Disconnected'
        : 'Disabled'

  const lastSyncLabel = status?.lastSyncedAt
    ? new Date(status.lastSyncedAt).toLocaleString()
    : 'Never'

  return (
    <section className="glass-card p-6 rounded-2xl space-y-4" data-testid="garmin-card">
      <h2 className="text-xl font-black">Garmin Connection</h2>
      <div
        className={`rounded-xl border border-white/10 px-4 py-3 ${
          status?.connected ? 'bg-emerald-500/10' : 'bg-slate-500/10'
        }`}
      >
        <p data-testid="garmin-status" className="text-sm uppercase tracking-wide">
          Status: {statusText}
        </p>
      </div>

      {(requestError || actionError) && (
        <p
          ref={statusRef}
          role="alert"
          className="toast toast-error"
          data-testid="garmin-error"
          tabIndex={-1}
        >
          {actionError || requestError}
        </p>
      )}
      {requestInFlight ? (
        <p role="status" aria-live="polite" data-testid="garmin-action-status">
          Processing Garmin request...
        </p>
      ) : null}

      <dl className="space-y-2" data-testid="garmin-meta">
        <div className="text-sm">
          <dt className="text-slate-400">Integration</dt>
          <dd data-testid="garmin-enabled">
            {status?.enabled ? 'Enabled' : 'Unavailable'}
          </dd>
        </div>
        <div className="text-sm">
          <dt className="text-slate-400">Connected</dt>
          <dd data-testid="garmin-connected">
            {status?.connected ? 'Yes' : 'No'}
          </dd>
        </div>
        {status?.hasRefreshToken && (
          <div className="text-sm">
            <dt className="text-slate-400">Refresh token</dt>
            <dd data-testid="garmin-refresh">Stored</dd>
          </div>
        )}
        <div className="text-sm">
          <dt className="text-slate-400">Last sync</dt>
          <dd data-testid="garmin-last-sync">
            {lastSyncLabel}
          </dd>
        </div>
      </dl>

      {status?.lastSyncSummary && (
        <p
          className="text-sm text-slate-300"
          role="status"
          aria-live="polite"
          data-testid="garmin-sync-summary"
          tabIndex={-1}
        >
          Last sync: {status.lastSyncSummary.imported} imported, {status.lastSyncSummary.duplicates} duplicates,
          {` ${status.lastSyncSummary.unsupported} unsupported, ${status.lastSyncSummary.invalid} invalid`}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {canConnect ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleConnect}
            aria-label="Connect Garmin"
            data-testid="garmin-connect-btn"
            aria-busy={requestInFlight}
            disabled={requestInFlight}
          >
            Connect Garmin
          </button>
        ) : null}
        {canDisconnect ? (
          <button
            type="button"
            className="btn btn-danger"
            onClick={handleDisconnect}
            aria-label="Disconnect Garmin"
            data-testid="garmin-disconnect-btn"
            aria-busy={requestInFlight}
            disabled={requestInFlight}
          >
            Disconnect Garmin
          </button>
        ) : null}
      </div>
    </section>
  )
}
