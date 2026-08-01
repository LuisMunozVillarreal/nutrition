import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { chmod, mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'vitest'
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

function workflowDependencyGraph(config, workflowName) {
  const workflowJobs = config.workflows?.[workflowName]?.jobs
  assert.ok(Array.isArray(workflowJobs), 'validation workflow jobs are unavailable')

  const graph = new Map()
  for (const entry of workflowJobs) {
    if (typeof entry === 'string') {
      graph.set(entry, [])
      continue
    }
    assert.ok(entry && typeof entry === 'object' && !Array.isArray(entry), 'invalid workflow job entry')
    const names = Object.keys(entry)
    assert.equal(names.length, 1, 'workflow job entry must have one job name')
    const jobName = names[0]
    const requires = entry[jobName]?.requires ?? []
    assert.ok(Array.isArray(requires), `${jobName} has invalid requirements`)
    graph.set(jobName, requires)
  }
  return graph
}

function transitiveRequirements(graph, jobName) {
  assert.ok(graph.has(jobName), `${jobName} is missing from the validation workflow`)
  const requirements = new Set()
  const visit = (current) => {
    for (const dependency of graph.get(current) ?? []) {
      assert.ok(graph.has(dependency), `${current} requires an unknown workflow job`)
      if (!requirements.has(dependency)) {
        requirements.add(dependency)
        visit(dependency)
      }
    }
  }
  visit(jobName)
  return requirements
}

function assertTransitivelyRequires(graph, jobName, requiredJobs) {
  const requirements = transitiveRequirements(graph, jobName)
  for (const requiredJob of requiredJobs) {
    assert.ok(requirements.has(requiredJob), `${jobName} is not gated by ${requiredJob}`)
  }
}

test('CI transports isolated E2E credentials only through backend stdin and always clears them', async () => {
  const config = await readRepoFile('.circleci/config.yml')

  assertContains(config, /E2E_RUN_TOKEN="\$\(openssl rand -hex 16\)"/, 'run token is not generated per run')
  assertContains(config, /E2E_RUN_MARKER="__e2e_run_\$\{E2E_RUN_TOKEN\}__"/, 'reserved run marker is not constructed')
  assertContains(config, /E2E_REGULAR_PASSWORD="\$\(openssl rand -hex 32\)"/, 'regular password is not generated per run')
  assertContains(config, /E2E_STAFF_PASSWORD="\$\(openssl rand -hex 32\)"/, 'staff password is not generated per run')
  assert.doesNotMatch(config, /export (?:E2E|CYPRESS_E2E)_/, 'E2E lifecycle values are exported globally')
  assertContains(
    config,
    /CYPRESS_E2E_REGULAR_EMAIL="\$E2E_REGULAR_EMAIL"[\s\S]*?CYPRESS_E2E_RUN_MARKER="\$E2E_RUN_MARKER"[\s\\]*\n\s*npm run cypress:run/,
    'Cypress aliases are not scoped to its single command',
  )
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
  const environmentLog = join(temporaryRoot, 'environment.log')
  const kubectlCount = join(temporaryRoot, 'kubectl-count')
  const opensslCount = join(temporaryRoot, 'openssl-count')
  const recordArgv = `
for argument in "$@"; do
  printf '%s\\n' "$argument" >>"$ARGV_LOG"
done
printf '%s\\n' -- >>"$ARGV_LOG"
`
  const recordEnvironment = `
command_name=\${0##*/}
for key in E2E_LIFECYCLE_PAYLOAD E2E_RUN_TOKEN E2E_RUN_MARKER E2E_REGULAR_EMAIL E2E_REGULAR_PASSWORD E2E_STAFF_EMAIL E2E_STAFF_PASSWORD CYPRESS_E2E_RUN_MARKER CYPRESS_E2E_REGULAR_EMAIL CYPRESS_E2E_REGULAR_PASSWORD CYPRESS_E2E_STAFF_EMAIL CYPRESS_E2E_STAFF_PASSWORD; do
  if [ -n "\${!key+x}" ]; then presence=present; else presence=absent; fi
  printf '%s|%s|%s=%s\\n' "$TEST_SCENARIO" "$command_name" "$key" "$presence" >>"$ENVIRONMENT_LOG"
done
`

  await writeExecutable(
    join(fakeBin, 'python3'),
    `#!/usr/bin/env bash
set -eu
${recordArgv}
${recordEnvironment}
printf '%s\\n' 'security-test-branch'
`,
  )
  await writeExecutable(
    join(fakeBin, 'openssl'),
    `#!/usr/bin/env bash
set -eu
${recordArgv}
${recordEnvironment}
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
${recordEnvironment}
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
${recordEnvironment}
[ "$CYPRESS_E2E_REGULAR_EMAIL" = 'e2e-regular-run-sentinel@example.com' ] || exit 91
[ "$CYPRESS_E2E_REGULAR_PASSWORD" = 'regular-sentinel' ] || exit 92
[ "$CYPRESS_E2E_STAFF_EMAIL" = 'e2e-staff-run-sentinel@example.com' ] || exit 93
[ "$CYPRESS_E2E_STAFF_PASSWORD" = 'staff-sentinel' ] || exit 94
[ "$CYPRESS_E2E_RUN_MARKER" = '__e2e_run_run-sentinel__' ] || exit 95
[ "$TEST_SCENARIO" != 'cypress-cleanup-fail' ] || exit 31
`,
  )
  await writeExecutable(
    join(fakeBin, 'sudo'),
    `#!/usr/bin/env bash
set -eu
${recordArgv}
${recordEnvironment}
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
${recordEnvironment}
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
  const rawLifecycleKeys = [
    'E2E_LIFECYCLE_PAYLOAD',
    'E2E_RUN_TOKEN',
    'E2E_RUN_MARKER',
    'E2E_REGULAR_EMAIL',
    'E2E_REGULAR_PASSWORD',
    'E2E_STAFF_EMAIL',
    'E2E_STAFF_PASSWORD',
  ]
  const cypressAliasKeys = [
    'CYPRESS_E2E_RUN_MARKER',
    'CYPRESS_E2E_REGULAR_EMAIL',
    'CYPRESS_E2E_REGULAR_PASSWORD',
    'CYPRESS_E2E_STAFF_EMAIL',
    'CYPRESS_E2E_STAFF_PASSWORD',
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
      await writeFile(environmentLog, '')
      await rm(kubectlCount, { force: true })
      await rm(opensslCount, { force: true })

      const result = await runShell(lifecycleStep.run.command, {
        cwd: new URL('../', import.meta.url),
        env: {
          ...process.env,
          PATH: `${fakeBin}:${process.env.PATH}`,
          ARGV_LOG: argvLog,
          ENVIRONMENT_LOG: environmentLog,
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

      const environmentPresence = (await readFile(environmentLog, 'utf8'))
        .trim()
        .split('\n')
        .filter(Boolean)
        .map((line) => {
          const [observedScenario, commandName, assignment] = line.split('|')
          const [key, presence] = assignment.split('=')
          return { observedScenario, commandName, key, presence }
        })
      assert.ok(environmentPresence.length > 0, `${scenario} recorded no process environments`)
      for (const observation of environmentPresence) {
        assert.equal(observation.observedScenario, scenario)
        if (observation.commandName === 'npm') {
          assert.equal(
            observation.presence,
            cypressAliasKeys.includes(observation.key) ? 'present' : 'absent',
            `${scenario} gave npm the wrong E2E environment key set`,
          )
        } else {
          assert.equal(
            observation.presence,
            'absent',
            `${scenario} exposed an E2E environment key to ${observation.commandName}`,
          )
        }
      }
      if (scenario.startsWith('cypress') || scenario === 'success' || scenario === 'cleanup-retry' || scenario === 'cleanup-fail') {
        for (const key of [...rawLifecycleKeys, ...cypressAliasKeys]) {
          assert.ok(
            environmentPresence.some(
              (observation) =>
                observation.commandName === 'npm' &&
                observation.key === key &&
                observation.presence === (cypressAliasKeys.includes(key) ? 'present' : 'absent'),
            ),
            `${scenario} did not observe npm's expected least-privilege environment`,
          )
        }
      } else {
        assert.ok(
          environmentPresence.every((observation) => observation.commandName !== 'npm'),
          `${scenario} unexpectedly reached Cypress`,
        )
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
          run_marker: '__e2e_run_run-sentinel__',
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
  assert.match(manager, /GarminConnection\.objects\.create\([\s\S]*?user=regular_user[\s\S]*?refresh_token_encrypted=/)
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

test('Cypress marks every shared catalog fixture and current-run selector', async () => {
  const fixtureHelper = await readRepoFile('webapp/cypress/support/e2eFixtures.ts')
  assert.match(fixtureHelper, /Cypress\.env\(['"]E2E_RUN_MARKER['"]\)/)
  assert.match(fixtureHelper, /\^__e2e_run_\[0-9a-f\]\{32\}__\$/)

  for (const [path, calls] of [
    ['webapp/cypress/support/step_definitions/products.ts', 1],
    ['webapp/cypress/support/step_definitions/recipes.ts', 1],
    ['webapp/cypress/support/step_definitions/cupboard.ts', 3],
  ]) {
    const source = await readRepoFile(path)
    assert.equal(
      source.match(/e2eFixtureName\(/g)?.length,
      calls,
      `${path} does not mark every fixture name and selector`,
    )
  }
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

test('workflow publication and deployment paths are transitively gated by complete validation', async () => {
  const config = parse(await readRepoFile('.circleci/config.yml'))
  const webappChecks = config.jobs?.['webapp-checks']
  assert.equal(webappChecks?.working_directory, '~/project/webapp')
  const webappCommands = webappChecks.steps
    .map((step) => step?.run?.command)
    .filter((command) => typeof command === 'string')
  assert.ok(webappCommands.includes('npm ci'), 'frontend dependency installation is missing')
  assert.ok(webappCommands.includes('npm test'), 'frontend tests are missing')
  assert.ok(
    webappCommands.includes('npx tsc --noEmit'),
    'accepted frontend typecheck is missing',
  )
  assert.ok(webappCommands.includes('npm run lint'), 'frontend lint is missing')

  const backendValidation = [
    'pytest',
    'bandit',
    'flake8',
    'black',
    'mypy',
    'pylint',
    'pylint-tests',
    'pydocstyle',
    'pydocstyle-tests',
  ]
  const frontendValidation = ['webapp-checks']
  const completeValidation = [...backendValidation, ...frontendValidation]
  const graph = workflowDependencyGraph(config, 'ValidationWorkflow')

  assertTransitivelyRequires(graph, 'backend-docker-build-tag-push', backendValidation)
  assertTransitivelyRequires(graph, 'webapp-docker-build-tag-push', frontendValidation)
  for (const deploymentJob of ['deploy-preview', 'deploy-production']) {
    assertTransitivelyRequires(graph, deploymentJob, [
      'backend-docker-build-tag-push',
      'webapp-docker-build-tag-push',
      ...completeValidation,
    ])
  }
  assertTransitivelyRequires(graph, 'cypress-e2e', ['deploy-preview', ...completeValidation])
})
