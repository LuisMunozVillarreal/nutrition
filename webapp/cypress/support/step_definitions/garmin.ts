import { Given, Then, When } from "@badeball/cypress-cucumber-preprocessor"

type GarminStatusFixture = {
  enabled: boolean
  connected: boolean
  hasRefreshToken: boolean
  lastSyncedAt: string | null
  lastSyncSummary: {
    imported: number
    duplicates: number
    unsupported: number
    invalid: number
  } | null
}

const garminDefaultStatus: GarminStatusFixture = {
  enabled: true,
  connected: false,
  hasRefreshToken: false,
  lastSyncedAt: null,
  lastSyncSummary: null,
}

const garminConnectedStatus: GarminStatusFixture = {
  ...garminDefaultStatus,
  enabled: true,
  connected: true,
  hasRefreshToken: true,
  lastSyncedAt: '2026-07-30T10:00:00.000Z',
  lastSyncSummary: {
    imported: 0,
    duplicates: 0,
    unsupported: 0,
    invalid: 0,
  },
}

function getGraphQLEndpoint(): string {
  const baseUrl = Cypress.config('baseUrl') || 'http://localhost:3000'
  const configuredEndpoint = Cypress.env('NEXT_PUBLIC_GRAPHQL_ENDPOINT') as
    | string
    | undefined

  const endpoint = configuredEndpoint?.trim() || '/graphql/'

  return new URL(endpoint, `${baseUrl}/`).href
}

function registerGarminIntercepts({
  status = [garminDefaultStatus],
  beginUrl = '/settings/garmin-callback?code=unit-code&state=unit-state',
  completeStatus = garminConnectedStatus,
  disconnectResult = true,
}: {
  status?: GarminStatusFixture | GarminStatusFixture[]
  beginUrl?: string
  completeStatus?: GarminStatusFixture
  disconnectResult?: boolean
}) {
  const queue = Array.isArray(status) ? [...status] : [status]
  const endpoint = getGraphQLEndpoint()

  cy.intercept('POST', endpoint, (req) => {
    const body = req.body as { operationName?: string }
    const operation = body?.operationName
    if (!operation) return

    if (operation === 'GarminSettingsStatusQuery') {
      const payload = queue.shift() ?? garminDefaultStatus
      req.reply({
        statusCode: 200,
        body: { data: { garminStatus: payload } },
      })
      req.alias = 'garminStatusQuery'
      return
    }

    if (operation === 'BeginGarminAuthorization') {
      req.reply({
        statusCode: 200,
        body: {
          data: {
            beginGarminAuthorization: {
              authorizationUrl: `http://localhost:3000${beginUrl}`,
              state: 'unit-state',
              expiresAt: '2026-07-31T10:00:00.000Z',
            },
          },
        },
      })
      req.alias = 'garminBeginAuthorization'
      return
    }

    if (operation === 'CompleteGarminAuthorization') {
      req.reply({
        statusCode: 200,
        body: { data: { completeGarminAuthorization: completeStatus } },
      })
      req.alias = 'garminCompleteAuthorization'
      return
    }

    if (operation === 'DisconnectGarmin') {
      req.reply({
        statusCode: 200,
        body: {
          data: { disconnectGarmin: disconnectResult },
        },
      })
      req.alias = 'garminDisconnect'
      return
    }
  }).as('garminGraphQL')
}

Given('Garmin integration is disconnected', () => {
  registerGarminIntercepts({
    status: garminDefaultStatus,
    beginUrl: '/settings/garmin-callback?code=unit-code&state=unit-state',
    completeStatus: garminConnectedStatus,
    disconnectResult: true,
  })
})

Given('Garmin integration is connected', () => {
  registerGarminIntercepts({
    status: [garminConnectedStatus, garminDefaultStatus],
    beginUrl: '/settings/garmin-callback?code=unit-code&state=unit-state',
    completeStatus: garminConnectedStatus,
    disconnectResult: true,
  })
})

When('I navigate to the settings page', () => {
  cy.visit('/settings')
  cy.get('[data-testid="settings-title"]', { timeout: 10000 })
    .should('be.visible')
})

When('I mock Garmin OAuth begin response with local callback URL', () => {
  registerGarminIntercepts({
    status: [garminDefaultStatus, garminConnectedStatus],
    beginUrl: '/settings/garmin-callback?code=unit-code&state=unit-state',
    completeStatus: garminConnectedStatus,
    disconnectResult: true,
  })
})

When('I click the Garmin connect button', () => {
  cy.get('[data-testid="garmin-connect-btn"]', { timeout: 10000 }).click()
  cy.wait('@garminBeginAuthorization')
})

When('I click the Garmin disconnect button', () => {
  cy.get('[data-testid="garmin-disconnect-btn"]', { timeout: 10000 })
    .should('be.visible')
    .click()

  cy.wait('@garminDisconnect')
  cy.wait('@garminStatusQuery')
})

Then('I should see Garmin as disconnected', () => {
  cy.get('[data-testid="garmin-connected"]', { timeout: 10000 })
    .should('contain.text', 'No')
})

Then('I should be redirected to the Garmin callback page', () => {
  cy.wait(100)
  cy.url({ timeout: 20000 }).should('include', '/settings/garmin-callback')
})

Then('I should return to the settings page after successful Garmin callback', () => {
  cy.get('[data-testid="garmin-callback-success"]', { timeout: 20000 })
    .should('be.visible')
  cy.location('pathname', { timeout: 20000 }).should('equal', '/settings')
})

Given('I visit Garmin callback with provider error', () => {
  cy.visit(
    '/settings/garmin-callback?error=access_denied&error_description=User%20cancelled',
  )
})

Then('I should see a Garmin callback error', () => {
  cy.get('[data-testid="garmin-callback-error"]', { timeout: 10000 })
    .should('be.visible')
    .and('contain.text', 'Garmin sign-in failed')
})
