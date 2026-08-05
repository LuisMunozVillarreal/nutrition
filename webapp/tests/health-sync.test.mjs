import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('steps page exposes Health Connect pairing and safe device management', async () => {
  const page = await readFile(
    new URL('../src/app/steps/page.tsx', import.meta.url),
    'utf8',
  )
  const panel = await readFile(
    new URL('../src/app/steps/HealthSyncPanel.tsx', import.meta.url),
    'utf8',
  )

  assert.match(page, /<HealthSyncPanel\s*\/>/)
  assert.match(page, /source/)
  assert.match(page, /syncedAt/)
  assert.match(page, /Health Connect/)
  assert.match(panel, /createHealthSyncPairingCode/)
  assert.match(panel, /healthSyncDevices/)
  assert.match(panel, /revokeHealthSyncDevice/)
  assert.match(panel, /Samsung Health/)
  assert.match(panel, /Health Connect/)
  assert.match(panel, /expiresAt/)
  assert.match(panel, /lastSuccessAt/)
  assert.match(panel, /revokeHealthSyncDevice:\s*boolean/)
  assert.match(panel, /if \(!data\.revokeHealthSyncDevice\)/)
  assert.doesNotMatch(panel, /tokenHash|tokenPrefix/)
})
