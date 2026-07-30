export type E2ERole = 'regular' | 'staff'

function requiredCypressEnvironment(name: string): string {
  const value = Cypress.env(name)
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`Missing required Cypress environment variable: ${name}`)
  }
  return value
}

export function e2eCredentials(role: E2ERole): { email: string; password: string } {
  const prefix = role.toUpperCase()
  return {
    email: requiredCypressEnvironment(`E2E_${prefix}_EMAIL`),
    password: requiredCypressEnvironment(`E2E_${prefix}_PASSWORD`),
  }
}

export function loginAsE2eUser(role: E2ERole): void {
  const { email, password } = e2eCredentials(role)
  // A prior feature can leave a valid NextAuth cookie in the shared browser.
  // Clear client state before visiting /login so AppShell cannot redirect an
  // already-authenticated session away before the credential form hydrates.
  cy.clearCookies()
  cy.clearLocalStorage()
  cy.visit('/login')
  cy.get('input[type="email"]', { timeout: 10000 }).type(email, { log: false })
  cy.get('input[type="password"]').type(password, { log: false })
  cy.get('button[type="submit"]').click()
  cy.url({ timeout: 15000 }).should('not.include', '/login')
  cy.get('body').should('be.visible')
}
