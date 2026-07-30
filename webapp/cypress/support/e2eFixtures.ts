const RUN_MARKER_PATTERN = /^__e2e_run_[0-9a-f]{32}__$/

export function e2eFixtureName(baseName: string): string {
  const marker = Cypress.env('E2E_RUN_MARKER')
  if (typeof marker !== 'string' || !RUN_MARKER_PATTERN.test(marker)) {
    throw new Error('Missing or invalid Cypress E2E run marker')
  }
  return `${baseName} ${marker}`
}
