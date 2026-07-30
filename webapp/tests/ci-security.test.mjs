import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const readRepoFile = (path) => readFile(new URL(`../../${path}`, import.meta.url), 'utf8')

function assertContains(source, pattern, message) {
  assert.ok(pattern.test(source), message)
}

test('CI generates isolated regular and staff credentials and always removes E2E accounts', async () => {
  const config = await readRepoFile('.circleci/config.yml')

  assertContains(config, /E2E_REGULAR_PASSWORD="\$\(openssl rand -hex 32\)"/, 'regular password is not generated per run')
  assertContains(config, /E2E_STAFF_PASSWORD="\$\(openssl rand -hex 32\)"/, 'staff password is not generated per run')
  assertContains(config, /export CYPRESS_E2E_REGULAR_EMAIL="\$E2E_REGULAR_EMAIL"/, 'regular email is not passed to Cypress')
  assertContains(config, /export CYPRESS_E2E_REGULAR_PASSWORD="\$E2E_REGULAR_PASSWORD"/, 'regular password is not passed to Cypress')
  assertContains(config, /export CYPRESS_E2E_STAFF_EMAIL="\$E2E_STAFF_EMAIL"/, 'staff email is not passed to Cypress')
  assertContains(config, /export CYPRESS_E2E_STAFF_PASSWORD="\$E2E_STAFF_PASSWORD"/, 'staff password is not passed to Cypress')
  assertContains(config, /trap cleanup EXIT/, 'E2E cleanup is not registered as an EXIT trap')
  assertContains(config, /python3 -m scripts\.manage_e2e_users seed/, 'E2E accounts are not seeded through the lifecycle script')
  assertContains(config, /python3 -m scripts\.manage_e2e_users cleanup/, 'E2E accounts are not cleaned through the lifecycle script')
  assertContains(config, /set \+x/, 'shell tracing is not disabled before secret generation')
  assert.ok(
    config.indexOf('trap cleanup EXIT') < config.indexOf('npm run cypress:run'),
    'cleanup is registered after Cypress starts',
  )
  assert.ok(
    !/create_user\([^\n]+password\s*=\s*['"][^$]/i.test(config),
    'CI contains a fixed account password',
  )
})

test('E2E account management keeps the default identity least-privileged', async () => {
  const manager = await readRepoFile('backend/scripts/manage_e2e_users.py')
  const seedDay = await readRepoFile('backend/scripts/seed_test_day.py')
  const loginSteps = await readRepoFile('webapp/cypress/support/step_definitions/login.ts')
  const authenticationSteps = await readRepoFile(
    'webapp/cypress/support/step_definitions/authentication.ts',
  )
  const credentials = await readRepoFile('webapp/cypress/support/e2eCredentials.ts')

  assert.match(manager, /create_e2e_user\([\s\S]*?is_staff=False/)
  assert.match(manager, /create_e2e_user\([^)]*E2E_STAFF_PASSWORD[\s\S]*?is_staff=True/)
  assert.match(manager, /User\.objects\.filter\(email__in=emails\)\.delete\(\)/)
  assert.match(seedDay, /os\.environ\["E2E_REGULAR_EMAIL"\]/)
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
