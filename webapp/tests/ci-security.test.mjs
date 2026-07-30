import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { chmod, mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { parse } from 'yaml'

const readRepoFile = (path) => readFile(new URL(`../../${path}`, import.meta.url), 'utf8')

function assertContains(source, pattern, message) {
  assert.ok(pattern.test(source), message)
}

function runShell(command, { cwd, env }) {
  return new Promise((resolve, reject) => {
    const child = spawn('bash', ['-o', 'pipefail', '-c', command], { cwd, env })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (chunk) => {
      stdout += chunk
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk
    })
    child.on('error', reject)
    child.on('close', (code, signal) => resolve({ code, signal, stdout, stderr }))
  })
}

async function writeExecutable(path, content) {
  await writeFile(path, content)
  await chmod(path, 0o755)
}

test('CI transports isolated E2E credentials only through backend stdin and always clears them', async () => {
  const config = await readRepoFile('.circleci/config.yml')

  assertContains(config, /E2E_REGULAR_PASSWORD="\$\(openssl rand -hex 32\)"/, 'regular password is not generated per run')
  assertContains(config, /E2E_STAFF_PASSWORD="\$\(openssl rand -hex 32\)"/, 'staff password is not generated per run')
  assertContains(config, /export CYPRESS_E2E_REGULAR_EMAIL="\$E2E_REGULAR_EMAIL"/, 'regular email is not passed to Cypress')
  assertContains(config, /export CYPRESS_E2E_REGULAR_PASSWORD="\$E2E_REGULAR_PASSWORD"/, 'regular password is not passed to Cypress')
  assertContains(config, /export CYPRESS_E2E_STAFF_EMAIL="\$E2E_STAFF_EMAIL"/, 'staff email is not passed to Cypress')
  assertContains(config, /export CYPRESS_E2E_STAFF_PASSWORD="\$E2E_STAFF_PASSWORD"/, 'staff password is not passed to Cypress')
  assertContains(config, /printf -v E2E_LIFECYCLE_PAYLOAD/, 'structured lifecycle payload is not built with a shell builtin')
  assertContains(config, /kubectl exec -i /, 'backend lifecycle stdin is not connected to kubectl')
  assertContains(
    config,
    /printf '%s\\n' "\$E2E_LIFECYCLE_PAYLOAD"[\s\\]*\| kubectl exec -i /,
    'backend lifecycle payload is not piped through stdin by a shell builtin',
  )
  assert.doesNotMatch(config, /<<<"\$E2E_LIFECYCLE_PAYLOAD"/, 'CircleCI expression parsing is triggered by a here-string')
  assert.doesNotMatch(
    config,
    /kubectl exec[^\n]*-- env[\s\S]*?E2E_(?:REGULAR|STAFF)_(?:EMAIL|PASSWORD)=/,
    'E2E credentials are included in kubectl or remote process arguments',
  )
  assertContains(config, /trap cleanup EXIT/, 'E2E cleanup is not registered as an EXIT trap')
  assertContains(config, /python3 -m scripts\.manage_e2e_users seed/, 'E2E accounts are not seeded through the lifecycle script')
  assertContains(config, /python3 -m scripts\.manage_e2e_users cleanup/, 'E2E accounts are not cleaned through the lifecycle script')
  assertContains(config, /python3 -m scripts\.seed_test_day/, 'test-day setup does not consume the lifecycle transport')
  assertContains(config, /unset E2E_LIFECYCLE_PAYLOAD/, 'lifecycle payload is not cleared during cleanup')
  assert.ok(
    config.indexOf('trap cleanup EXIT') < config.indexOf('python3 -m scripts.manage_e2e_users seed'),
    'cleanup is registered after account seeding starts',
  )
  assert.ok(
    config.indexOf('trap cleanup EXIT') < config.indexOf('npm run cypress:run'),
    'cleanup is registered after Cypress starts',
  )
  assert.ok(
    !/create_user\([^\n]+password\s*=\s*['"][^$]/i.test(config),
    'CI contains a fixed account password',
  )
})

test('embedded E2E lifecycle keeps sentinels off argv and output across failures', async () => {
  const configSource = await readRepoFile('.circleci/config.yml')
  const config = parse(configSource)
  const lifecycleStep = config.jobs['cypress-e2e'].steps.find(
    (step) => step.run?.name === 'Seed, Run Cypress, and Cleanup E2E Accounts',
  )
  assert.equal(typeof lifecycleStep?.run?.command, 'string')

  const temporaryRoot = await mkdtemp(join(tmpdir(), 'e2e-lifecycle-test-'))
  const fakeBin = join(temporaryRoot, 'bin')
  await mkdir(fakeBin)

  const argvLog = join(temporaryRoot, 'argv.log')
  const kubectlCount = join(temporaryRoot, 'kubectl-count')
  const opensslCount = join(temporaryRoot, 'openssl-count')
  const recordArgv = `
for argument in "$@"; do
  printf '%s\\n' "$argument" >>"$ARGV_LOG"
done
printf '%s\\n' -- >>"$ARGV_LOG"
`

  await writeExecutable(
    join(fakeBin, 'openssl'),
    `#!/usr/bin/env bash
set -eu
${recordArgv}
count=0
if [ -r "$OPENSSL_COUNT" ]; then IFS= read -r count <"$OPENSSL_COUNT"; fi
count=$((count + 1))
printf '%s\\n' "$count" >"$OPENSSL_COUNT"
case "$count" in
  1) printf '%s\\n' 'run-sentinel' ;;
  2) printf '%s\\n' 'regular-sentinel' ;;
  3) printf '%s\\n' 'staff-sentinel' ;;
  *) exit 90 ;;
esac
`,
  )
  await writeExecutable(
    join(fakeBin, 'kubectl'),
    `#!/usr/bin/env bash
set -eu
${recordArgv}
count=0
if [ -r "$KUBECTL_COUNT" ]; then IFS= read -r count <"$KUBECTL_COUNT"; fi
count=$((count + 1))
printf '%s\\n' "$count" >"$KUBECTL_COUNT"
IFS= read -r payload
printf '%s\\n' "$payload" >"$OBSERVATION_DIR/stdin-$count.json"
case " $* " in
  *' scripts.manage_e2e_users seed '*)
    [ "$TEST_SCENARIO" != 'seed-fail' ] || exit 23
    ;;
  *' scripts.manage_e2e_users cleanup '*)
    case "$TEST_SCENARIO" in
      cleanup-retry) [ "$count" -ge 4 ] || exit 29 ;;
      *cleanup-fail) exit 29 ;;
    esac
    ;;
esac
`,
  )
  await writeExecutable(
    join(fakeBin, 'npm'),
    `#!/usr/bin/env bash
set -eu
${recordArgv}
[ "$CYPRESS_E2E_REGULAR_EMAIL" = 'e2e-regular-run-sentinel@example.com' ] || exit 91
[ "$CYPRESS_E2E_REGULAR_PASSWORD" = 'regular-sentinel' ] || exit 92
[ "$CYPRESS_E2E_STAFF_EMAIL" = 'e2e-staff-run-sentinel@example.com' ] || exit 93
[ "$CYPRESS_E2E_STAFF_PASSWORD" = 'staff-sentinel' ] || exit 94
[ "$TEST_SCENARIO" != 'cypress-cleanup-fail' ] || exit 31
`,
  )
  await writeExecutable(
    join(fakeBin, 'sudo'),
    `#!/usr/bin/env bash
set -eu
${recordArgv}
if [ "\${1:-}" = 'tee' ]; then
  while IFS= read -r _line; do :; done || true
fi
`,
  )
  await writeExecutable(
    join(fakeBin, 'envsubst'),
    `#!/usr/bin/env bash
set -eu
${recordArgv}
while IFS= read -r _line; do :; done || true
`,
  )

  const sentinels = [
    'run-sentinel',
    'regular-sentinel',
    'staff-sentinel',
    'e2e-regular-run-sentinel@example.com',
    'e2e-staff-run-sentinel@example.com',
  ]
  const scenarios = [
    ['success', 0, 3],
    ['seed-fail', 23, 2],
    ['cleanup-retry', 0, 4],
    ['cypress-cleanup-fail', 31, 4],
    ['cleanup-fail', 29, 4],
  ]

  try {
    for (const [scenario, expectedStatus, expectedBackendCalls] of scenarios) {
      const observationDir = join(temporaryRoot, scenario)
      await mkdir(observationDir)
      await writeFile(argvLog, '')
      await rm(kubectlCount, { force: true })
      await rm(opensslCount, { force: true })

      const result = await runShell(lifecycleStep.run.command, {
        cwd: new URL('../', import.meta.url),
        env: {
          ...process.env,
          PATH: `${fakeBin}:${process.env.PATH}`,
          ARGV_LOG: argvLog,
          KUBECTL_COUNT: kubectlCount,
          OPENSSL_COUNT: opensslCount,
          OBSERVATION_DIR: observationDir,
          TEST_SCENARIO: scenario,
          CIRCLE_BRANCH: 'security-test-branch',
          BASE_DOMAIN: 'example.com',
        },
      })

      assert.equal(result.signal, null)
      assert.equal(result.code, expectedStatus, `${scenario} returned the wrong status`)
      const observedArgv = await readFile(argvLog, 'utf8')
      for (const sentinel of sentinels) {
        assert.doesNotMatch(observedArgv, new RegExp(sentinel), `${scenario} leaked through argv`)
        assert.doesNotMatch(result.stdout, new RegExp(sentinel), `${scenario} leaked through stdout`)
        assert.doesNotMatch(result.stderr, new RegExp(sentinel), `${scenario} leaked through stderr`)
      }

      for (let call = 1; call <= expectedBackendCalls; call += 1) {
        const payload = JSON.parse(
          await readFile(join(observationDir, `stdin-${call}.json`), 'utf8'),
        )
        assert.deepEqual(payload, {
          regular_email: 'e2e-regular-run-sentinel@example.com',
          regular_password: 'regular-sentinel',
          staff_email: 'e2e-staff-run-sentinel@example.com',
          staff_password: 'staff-sentinel',
        })
      }
    }
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true })
  }
})

test('E2E account management keeps the default identity least-privileged', async () => {
  const manager = await readRepoFile('backend/scripts/manage_e2e_users.py')
  const seedDay = await readRepoFile('backend/scripts/seed_test_day.py')
  const loginSteps = await readRepoFile('webapp/cypress/support/step_definitions/login.ts')
  const authenticationSteps = await readRepoFile(
    'webapp/cypress/support/step_definitions/authentication.ts',
  )
  const credentials = await readRepoFile('webapp/cypress/support/e2eCredentials.ts')

  assert.match(manager, /create_e2e_user\([\s\S]*?payload\.regular_password[\s\S]*?is_staff=False/)
  assert.match(manager, /create_e2e_user\([\s\S]*?payload\.staff_password[\s\S]*?is_staff=True/)
  assert.match(manager, /read_lifecycle_payload\(sys\.stdin\)/)
  assert.match(manager, /email__in=\[payload\.regular_email, payload\.staff_email\]/)
  assert.match(seedDay, /read_lifecycle_payload\(sys\.stdin\)/)
  assert.match(seedDay, /User\.objects\.get\(email=payload\.regular_email\)/)
  assert.doesNotMatch(seedDay, /is_staff\s*=\s*True/)

  assert.match(loginSteps, /e2eCredentials\('regular'\)/)
  assert.match(authenticationSteps, /loginAsE2eUser\('regular'\)/)
  assert.match(authenticationSteps, /loginAsE2eUser\('staff'\)/)
  assert.match(credentials, /requiredCypressEnvironment\(`E2E_\$\{prefix\}_PASSWORD`\)/)
  assert.match(credentials, /cy\.clearCookies\(\)/)
  assert.match(credentials, /cy\.clearLocalStorage\(\)/)
  assert.match(credentials, /cy\.session\(/)
  assert.match(credentials, /cacheAcrossSpecs: true/)
  assert.match(credentials, /cy\.location\('pathname', \{ timeout: 30000 \}\)/)
  assert.match(credentials, /input\[type=\\?"email\\?"\][\s\S]*timeout: 10000/)
  assert.match(credentials, /\.type\(password, \{ log: false \}\)/)
  assert.doesNotMatch(`${loginSteps}\n${credentials}`, /\.type\(['"][^'"]+['"]\)/)
})

test('shared-catalog write scenarios explicitly use the staff E2E identity', async () => {
  for (const path of [
    'webapp/cypress/e2e/products.feature',
    'webapp/cypress/e2e/recipes.feature',
    'webapp/cypress/e2e/cupboard.feature',
  ]) {
    const feature = await readRepoFile(path)
    assert.match(feature, /Scenario: (?:Create|Add)[^\n]*\n\s+Given I am logged in as staff/)
  }
})

test('frontend tests and accepted typecheck gate every image publication job', async () => {
  const config = await readRepoFile('.circleci/config.yml')
  const checksJob = config.match(/\n  webapp-checks:\n([\s\S]*?)\n  [a-z][\w-]+:\n/)?.[1] ?? ''

  assert.match(checksJob, /working_directory: ~\/project\/webapp/)
  assert.match(checksJob, /command: npm ci/)
  assert.match(checksJob, /command: npm test/)
  assert.match(checksJob, /command: npx tsc --noEmit --ignoreDeprecations 6\.0/)
  assert.doesNotMatch(checksJob, /eslint/i)

  for (const job of ['backend-docker-build-tag-push', 'webapp-docker-build-tag-push']) {
    const workflowJob = new RegExp(
      `- ${job}:\\n(?: {10}[^\\n]*\\n)*? {10}requires:\\n {12}- webapp-checks`,
    )
    assertContains(config, workflowJob, `${job} is not gated by webapp-checks`)
  }
})
