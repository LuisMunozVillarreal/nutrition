'use client'

import { useCallback, useState } from 'react'
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

const SYNC_GARMIN_MUTATION = gql`
  mutation SyncGarmin {
    syncGarmin {
      imported
      duplicates
      unsupported
      invalid
    }
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

type SyncActionState = 'idle' | 'syncing'

interface GarminConnectProps {
  status: GarminStatus | null
  loading: boolean
  requestError: string | null
  onStatusRefresh: () => void
}

function resolveError(
  error: unknown,
): string {
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
  const [syncAction, setSyncAction] = useState<SyncActionState>('idle')
  const [syncSummary, setSyncSummary] = useState<GarminSyncSummary | null>(null)

  const clearMessages = useCallback(() => {
    setActionError(null)
    setSyncSummary(null)
  }, [])

  const refreshAndReset = useCallback(() => {
    clearMessages()
    onStatusRefresh()
  }, [clearMessages, onStatusRefresh])

  const handleConnect = async () => {
    clearMessages()
    try {
      const response = await graphqlRequest<{
        beginGarminAuthorization: GarminAuthStart
      }>(BEGIN_GARMIN_AUTHORIZATION_MUTATION)

      if (typeof window !== 'undefined') {
        window.location.assign(response.beginGarminAuthorization.authorizationUrl)
      }
    } catch (error) {
      setActionError(resolveError(error))
    }
  }

  const handleDisconnect = async () => {
    clearMessages()
    const confirmed = window.confirm('Disconnect Garmin integration?')
    if (!confirmed || !status?.enabled || !status.connected) return

    try {
      const response = await graphqlRequest<{ disconnectGarmin: boolean }>(
        DISCONNECT_GARMIN_MUTATION,
      )
      if (response.disconnectGarmin) {
        refreshAndReset()
      } else {
        setActionError('Garmin was already disconnected.')
      }
    } catch (error) {
      setActionError(resolveError(error))
    }
  }

  const handleSync = async () => {
    clearMessages()
    if (!status?.connected || !status.enabled) return
    setSyncAction('syncing')
    try {
      const response = await graphqlRequest<{ syncGarmin: GarminSyncSummary }>(
        SYNC_GARMIN_MUTATION,
      )
      setSyncSummary(response.syncGarmin)
      refreshAndReset()
    } catch (error) {
      setActionError(resolveError(error))
    } finally {
      setSyncAction('idle')
    }
  }

  if (loading) {
    return (
      <div className="glass-card p-6 rounded-2xl" data-testid="garmin-loading">
        Loading Garmin status...
      </div>
    )
  }

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
        <p className="toast toast-error" data-testid="garmin-error">
          {actionError || requestError}
        </p>
      )}

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
          <dd data-testid="garmin-last-sync">{lastSyncLabel}</dd>
        </div>
      </dl>

      {syncSummary && (
        <p className="text-sm text-slate-300" data-testid="garmin-sync-summary">
          Last sync: {syncSummary.imported} imported, {syncSummary.duplicates} duplicates,
          {` ${syncSummary.unsupported} unsupported, ${syncSummary.invalid} invalid`}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {status?.enabled && !status.connected ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleConnect}
            aria-label="Connect Garmin"
            data-testid="garmin-connect-btn"
          >
            Connect Garmin
          </button>
        ) : null}
        {status?.enabled && status.connected ? (
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleSync}
              disabled={syncAction === 'syncing'}
              aria-label="Sync Garmin data"
              data-testid="garmin-sync-btn"
            >
              {syncAction === 'syncing' ? 'Syncing…' : 'Sync Now'}
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={handleDisconnect}
              aria-label="Disconnect Garmin"
              data-testid="garmin-disconnect-btn"
            >
              Disconnect Garmin
            </button>
          </>
        ) : null}
      </div>
    </section>
  )
}
