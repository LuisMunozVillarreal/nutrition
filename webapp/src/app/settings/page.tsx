'use client'

import { useCallback, useEffect, useState } from 'react'
import GarminConnect, { GarminStatus } from '@/components/GarminConnect'
import { graphqlRequest, gql } from '@/lib/graphql'

const GARMIN_STATUS_QUERY = gql`
  query GarminSettingsStatusQuery {
    garminStatus {
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

interface GarminConnectionSettingsState {
  garminStatus: GarminStatus | null
}

export default function SettingsPage() {
  const [status, setStatus] = useState<GarminStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadStatus = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await graphqlRequest<GarminConnectionSettingsState>(
        GARMIN_STATUS_QUERY,
      )
      setStatus(response.garminStatus)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Unable to load Garmin integration status.',
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadStatus()
  }, [loadStatus])

  return (
    <main>
      <h1 className="page-title mb-6" data-testid="settings-title">
        Settings
      </h1>
      <GarminConnect
        status={status}
        loading={loading}
        requestError={error}
        onStatusRefresh={loadStatus}
      />
    </main>
  )
}
