import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { parseAllDocuments } from 'yaml'

const repoFile = (path) =>
  readFile(new URL(`../../${path}`, import.meta.url), 'utf8')

function yamlDocuments(source) {
  return parseAllDocuments(source).map((document) => document.toJSON())
}

function workloadContainer(document) {
  if (document.kind === 'Deployment') {
    return document.spec.template.spec.containers[0]
  }
  if (document.kind === 'CronJob') {
    return document.spec.jobTemplate.spec.template.spec.containers[0]
  }
  throw new Error(`Unsupported workload kind: ${document.kind}`)
}

function garminEnvironment(document) {
  return new Map(
    workloadContainer(document)
      .env.filter(({ name }) => name.startsWith('GARMIN_'))
      .map((entry) => [entry.name, entry]),
  )
}

function configuredGarminSettings(source) {
  return new Set(
    [...source.matchAll(/ENV\.(?:bool|str|int|list)\(\s*["'](GARMIN_[A-Z0-9_]+)["']/g)]
      .map((match) => match[1]),
  )
}

function referencedSecretKeys(document, secretName) {
  return new Set(
    workloadContainer(document).env
      .map((entry) => entry.valueFrom?.secretKeyRef)
      .filter((reference) => reference?.name === secretName)
      .map((reference) => reference.key),
  )
}

test('Kustomize Garmin scheduler has production-only activation and full backend parity', async () => {
  const [backendSource, schedulerSource, kustomizationSource, productionSource, settingsSource] =
    await Promise.all([
      repoFile('platform/k8s/base/backend.yaml'),
      repoFile('platform/k8s/base/garmin-sync-cronjob.yaml'),
      repoFile('platform/k8s/base/kustomization.yaml'),
      repoFile('platform/k8s/overlays/production/kustomization.yaml'),
      repoFile('backend/config/settings.py'),
    ])

  const backend = yamlDocuments(backendSource).find(
    (document) => document.kind === 'Deployment' && document.metadata.name === 'nutrition-backend',
  )
  const scheduler = yamlDocuments(schedulerSource).find(
    (document) => document.kind === 'CronJob' && document.metadata.name === 'nutrition-garmin-sync',
  )
  assert.ok(backend)
  assert.ok(scheduler)

  const expectedNames = [...configuredGarminSettings(settingsSource)].sort()
  assert.deepEqual([...garminEnvironment(backend).keys()].sort(), expectedNames)
  assert.deepEqual([...garminEnvironment(scheduler).keys()].sort(), expectedNames)

  assert.equal(scheduler.spec.suspend, true)
  assert.equal(scheduler.spec.concurrencyPolicy, 'Forbid')
  assert.ok(scheduler.spec.startingDeadlineSeconds >= 300)
  assert.ok(scheduler.spec.successfulJobsHistoryLimit >= 1)
  assert.ok(scheduler.spec.failedJobsHistoryLimit >= 1)
  assert.ok(scheduler.spec.jobTemplate.spec.activeDeadlineSeconds > 0)
  assert.equal(scheduler.spec.jobTemplate.spec.template.spec.restartPolicy, 'Never')
  assert.equal(scheduler.spec.jobTemplate.spec.template.spec.automountServiceAccountToken, false)
  assert.deepEqual(workloadContainer(scheduler).command, ['python', 'manage.py', 'sync_garmin'])
  assert.equal(workloadContainer(scheduler).securityContext.runAsNonRoot, true)
  assert.equal(workloadContainer(scheduler).securityContext.allowPrivilegeEscalation, false)
  assert.deepEqual(workloadContainer(scheduler).securityContext.capabilities.drop, ['ALL'])

  const baseKustomization = yamlDocuments(kustomizationSource)[0]
  assert.ok(baseKustomization.resources.includes('garmin-sync-cronjob.yaml'))
  const productionKustomization = yamlDocuments(productionSource)[0]
  assert.ok(productionKustomization.patches.some(({ path }) => path === 'garmin-sync-enable-patch.yaml'))
})

test('disabled Garmin rollout uses optional Secret refs and documents every referenced key', async () => {
  const [backendSource, schedulerSource, readme] = await Promise.all([
    repoFile('platform/k8s/base/backend.yaml'),
    repoFile('platform/k8s/base/garmin-sync-cronjob.yaml'),
    repoFile('platform/kube/README.md'),
  ])
  const backend = yamlDocuments(backendSource).find((document) => document.kind === 'Deployment')
  const scheduler = yamlDocuments(schedulerSource)[0]

  for (const workload of [backend, scheduler]) {
    const env = garminEnvironment(workload)
    assert.equal(env.get('GARMIN_ENABLED').value, 'false')
    for (const entry of env.values()) {
      const reference = entry.valueFrom?.secretKeyRef
      if (reference?.name === 'nutrition-garmin-config') {
        assert.equal(reference.optional, true, `${entry.name} is rollout-blocking`)
      }
    }
  }

  const backendKeys = referencedSecretKeys(backend, 'nutrition-garmin-config')
  const schedulerKeys = referencedSecretKeys(scheduler, 'nutrition-garmin-config')
  assert.deepEqual([...schedulerKeys].sort(), [...backendKeys].sort())
  for (const key of backendKeys) {
    assert.match(readme, new RegExp(`--from-literal=${key}=<[^>]+>`))
  }
  assert.match(readme, /GARMIN_ENABLED=false/)
  assert.match(readme, /at least one of .*token-encryption-keys.*token-encryption-key/is)
})

test('Helmfile exposes a complete, disabled-by-default Garmin configuration and scheduler', async () => {
  const [helmfile, productionValues, stagingValues, settingsSource, chartValues, schedulerTemplate, readme] = await Promise.all([
    repoFile('platform/kube/helmfile.d/10-nutrition.yaml'),
    repoFile('platform/kube/helmfile.d/production.values.yaml-tmpl'),
    repoFile('platform/kube/helmfile.d/staging.values.yaml-tmpl'),
    repoFile('backend/config/settings.py'),
    repoFile('backend/platform/kube/values.yaml'),
    repoFile('backend/platform/kube/templates/cronjob-garmin-sync.yaml'),
    repoFile('platform/kube/README.md'),
  ])

  const expectedNames = [...configuredGarminSettings(settingsSource)]
  for (const name of expectedNames) {
    assert.match(helmfile, new RegExp(`name: ${name}\\n`), `${name} is missing from Helmfile`)
  }
  for (const valueName of [
    'enabled',
    'authorizationUrl',
    'tokenUrl',
    'activitiesUrl',
    'revokeTokenUrl',
    'providerOrigins',
    'callbackUrl',
    'callbackAllowedOrigins',
    'scopes',
    'requestTimeoutSeconds',
    'activityMaxPages',
    'activitySyncBatchSize',
    'activitiesLimit',
    'activityMaxTotalItems',
    'stateTtlSeconds',
    'stateMaxInFlight',
    'tokenMaxTtlSeconds',
    'activityEndpointMaxResponseBytes',
    'activityEndpointMaxTotalBytes',
    'tokenEndpointMaxResponseBytes',
  ]) {
    assert.ok(helmfile.includes(`.Values.garmin.${valueName}`), `${valueName} is not wired`)
  }

  for (const source of [productionValues, stagingValues]) {
    const values = yamlDocuments(source)[0]
    assert.equal(values.garmin.enabled, false)
    assert.equal(values.garmin.sync.enabled, false)
    assert.equal(values.garmin.sync.suspend, true)
    assert.equal(values.garmin.sync.concurrencyPolicy, 'Forbid')
    assert.notEqual(values.garmin.providerOrigins, values.garmin.callbackAllowedOrigins)
    assert.ok(values.garmin.authorizationUrl.startsWith(values.garmin.providerOrigins))
    assert.ok(values.garmin.callbackUrl.startsWith(values.garmin.callbackAllowedOrigins))
  }

  const defaults = yamlDocuments(chartValues)[0]
  assert.equal(defaults.garminSync.enabled, false)
  assert.equal(defaults.garminSync.suspend, true)
  assert.equal(defaults.garminSync.concurrencyPolicy, 'Forbid')
  assert.match(schedulerTemplate, /serviceAccountName: \{\{ include "nutrition\.serviceAccountName" \. \}\}/)
  assert.match(schedulerTemplate, /image: \{\{ \.Values\.image\.repository \}\}:\{\{ include "nutrition\.imageTag" \. \}\}/)
  assert.match(schedulerTemplate, /with \.Values\.env[\s\S]*?toYaml \./)
  assert.match(schedulerTemplate, /- python\n\s+- manage\.py\n\s+- sync_garmin/)
  assert.match(helmfile, /garminSync:[\s\S]*?enabled: \{\{ \.Values\.garmin\.sync\.enabled \}\}/)
  assert.match(helmfile, /suspend: \{\{ \.Values\.garmin\.sync\.suspend \}\}/)
  assert.match(readme, /production\.values\.yaml[\s\S]*?garmin\.enabled[\s\S]*?garmin\.sync\.enabled[\s\S]*?garmin\.sync\.suspend/is)
  assert.match(readme, /staging[\s\S]*?preview[\s\S]*?suspended/is)
})
