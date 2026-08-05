'use client'

import { useCallback, useEffect, useState } from 'react'
import { graphqlRequest, gql } from '@/lib/graphql'

const DEVICES_QUERY = gql`
  query HealthSyncDevices {
    healthSyncDevices {
      id
      name
      lastSeenAt
      lastSuccessAt
      expiresAt
      createdAt
    }
  }
`

const CREATE_PAIRING_CODE = gql`
  mutation CreateHealthSyncPairingCode {
    createHealthSyncPairingCode {
      code
      expiresAt
    }
  }
`

const REVOKE_DEVICE = gql`
  mutation RevokeHealthSyncDevice($id: ID!) {
    revokeHealthSyncDevice(id: $id)
  }
`

interface HealthSyncDevice {
  id: string
  name: string
  lastSeenAt: string | null
  lastSuccessAt: string | null
  expiresAt: string
  createdAt: string
}

interface PairingCode {
  code: string
  expiresAt: string
}

export default function HealthSyncPanel() {
  const [devices, setDevices] = useState<HealthSyncDevice[]>([])
  const [pairing, setPairing] = useState<PairingCode | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadDevices = useCallback(async () => {
    try {
      const data = await graphqlRequest<{ healthSyncDevices: HealthSyncDevice[] }>(
        DEVICES_QUERY,
      )
      setDevices(data.healthSyncDevices)
    } catch {
      setError('Could not load paired health devices.')
    }
  }, [])

  useEffect(() => { void loadDevices() }, [loadDevices])

  useEffect(() => {
    if (!pairing) return undefined
    const delay = Math.max(0, new Date(pairing.expiresAt).getTime() - Date.now())
    const timeout = window.setTimeout(() => setPairing(null), delay)
    return () => window.clearTimeout(timeout)
  }, [pairing])

  const createPairingCode = async () => {
    setBusy(true)
    setError(null)
    setPairing(null)
    try {
      const data = await graphqlRequest<{
        createHealthSyncPairingCode: PairingCode
      }>(CREATE_PAIRING_CODE)
      setPairing(data.createHealthSyncPairingCode)
    } catch {
      setError('Could not create a pairing code. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const revokeDevice = async (device: HealthSyncDevice) => {
    if (!confirm(`Disconnect ${device.name}?`)) return
    setBusy(true)
    setError(null)
    try {
      const data = await graphqlRequest<{
        revokeHealthSyncDevice: boolean
      }>(REVOKE_DEVICE, { id: device.id })
      if (!data.revokeHealthSyncDevice) {
        setError('The device was already disconnected or is no longer available.')
        await loadDevices()
        return
      }
      await loadDevices()
    } catch {
      setError('Could not disconnect the device.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="glass-card rounded-xl p-5 mb-6" aria-labelledby="health-sync-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h2 id="health-sync-title" className="text-lg font-semibold text-white">
            Samsung Health step sync
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Samsung Health shares your watch data with Health Connect on your phone.
            Pair the Nutrition Health Sync Android companion to import daily totals.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={createPairingCode}
        >
          {busy ? 'Working…' : 'Pair Android phone'}
        </button>
      </div>

      {pairing && (
        <div className="mt-4 rounded-lg border border-violet-500/30 bg-violet-500/10 p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-violet-300">
            One-time pairing code
          </p>
          <p className="mt-1 font-mono text-3xl tracking-[0.25em] text-white" data-testid="pairing-code">
            {pairing.code}
          </p>
          <p className="mt-2 text-xs text-slate-400">
            Enter this code in the Android companion before{' '}
            {new Date(pairing.expiresAt).toLocaleTimeString()}. It can only be used once.
          </p>
        </div>
      )}

      {error && <p className="mt-4 text-sm text-red-300" role="alert">{error}</p>}

      <div className="mt-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Paired devices
        </h3>
        {devices.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No Android companion is paired yet.</p>
        ) : (
          <ul className="mt-2 divide-y divide-white/5">
            {devices.map((device) => (
              <li key={device.id} className="flex items-center justify-between gap-4 py-3">
                <div>
                  <p className="text-sm font-medium text-slate-200">{device.name}</p>
                  <p className="text-xs text-slate-500">
                    {device.lastSuccessAt
                      ? `Last synced ${new Date(device.lastSuccessAt).toLocaleString()}`
                      : `Paired ${new Date(device.createdAt).toLocaleString()}`}
                    {' · '}
                    Credential expires {new Date(device.expiresAt).toLocaleDateString()}
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={busy}
                  onClick={() => void revokeDevice(device)}
                >
                  Disconnect
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
