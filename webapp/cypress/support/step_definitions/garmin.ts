import { Given, Then, When } from '@badeball/cypress-cucumber-preprocessor'

function getGraphQLEndpoint(): string {
  const baseUrl = Cypress.config('baseUrl') || 'http://localhost:3000'
  const configuredEndpoint = Cypress.env('NEXT_PUBLIC_GRAPHQL_ENDPOINT') as
    | string
    | undefined
  const endpoint = configuredEndpoint?.trim() || '/graphql/'

  return new URL(endpoint, `${baseUrl}/`).href
}

function expectBearerAuthorization(headers: Record<string, unknown>): void {
  const authorization = headers.authorization
  expect(authorization, 'backend bearer authorization')
    .to.be.a('string')
    .and.match(/^Bearer\s+\S+$/)
}

function registerGarminPassthroughAliases(): void {
  const endpoint = getGraphQLEndpoint()
  let statusRequests = 0

  cy.intercept('POST', endpoint, (req) => {
    const body = req.body as { operationName?: string }
    const operation = body?.operationName

    if (operation === 'GarminSettingsStatusQuery') {
      req.alias =
        statusRequests++ === 0
          ? 'garminStatusInitial'
          : 'garminStatusAfterDisconnect'
    } else if (operation === 'DisconnectGarmin') {
      req.alias = 'garminDisconnect'
    } else if (operation === 'CompleteGarminAuthorization') {
      req.alias = 'garminStateRejection'
    } else if (operation === 'CancelGarminAuthorization') {
      req.alias = 'garminAuthorizationCancelled'
    }

    req.continue()
  })
}

function requestGarminStatus() {
  return cy.request('/api/auth/session').then((sessionResponse) => {
    const accessToken = sessionResponse.body?.accessToken
    expect(accessToken, 'session access token').to.be.a('string').and.not.be.empty

    return cy.request({
      method: 'POST',
      url: getGraphQLEndpoint(),
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
      body: {
        operationName: 'GarminPersistedStatusQuery',
        query: `
          query GarminPersistedStatusQuery {
            garminStatus {
              enabled
              connected
              hasRefreshToken
            }
          }
        `,
      },
    })
  })
}

Given('Garmin GraphQL requests use the deployed backend', () => {
  registerGarminPassthroughAliases()
})

When('I navigate to the settings page', () => {
  cy.visit('/settings')
  cy.get('[data-testid="settings-title"]', { timeout: 10000 }).should(
    'be.visible',
  )
})

Then('the deployed backend should report the seeded Garmin connection', () => {
  cy.wait('@garminStatusInitial').then(({ request, response }) => {
    expectBearerAuthorization(request.headers)
    expect(response?.statusCode).to.equal(200)
    expect(response?.body?.errors).to.equal(undefined)
    expect(response?.body?.data?.garminStatus).to.include({
      connected: true,
      hasRefreshToken: true,
    })
  })
  cy.get('[data-testid="garmin-connected"]', { timeout: 10000 }).should(
    'contain.text',
    'Yes',
  )
})

When('I disconnect Garmin through the deployed backend', () => {
  cy.window().then((window) => {
    cy.stub(window, 'confirm').returns(true)
  })
  cy.get('[data-testid="garmin-disconnect-btn"]', { timeout: 10000 })
    .should('be.visible')
    .click()

  cy.wait('@garminDisconnect').then(({ request, response }) => {
    expectBearerAuthorization(request.headers)
    expect(response?.statusCode).to.equal(200)
    expect(response?.body?.errors).to.equal(undefined)
    expect(response?.body?.data?.disconnectGarmin).to.equal(true)
  })
  cy.wait('@garminStatusAfterDisconnect').then(({ request, response }) => {
    expectBearerAuthorization(request.headers)
    expect(response?.statusCode).to.equal(200)
    expect(response?.body?.errors).to.equal(undefined)
    expect(response?.body?.data?.garminStatus).to.include({
      connected: false,
      hasRefreshToken: false,
    })
  })
})

Then('the real Garmin disconnect should remain persisted', () => {
  cy.get('[data-testid="garmin-connected"]', { timeout: 10000 }).should(
    'contain.text',
    'No',
  )
  requestGarminStatus().then((response) => {
    expect(response.status).to.equal(200)
    expect(response.body?.errors).to.equal(undefined)
    expect(response.body?.data?.garminStatus).to.include({
      connected: false,
      hasRefreshToken: false,
    })
  })
})

Given('I submit an untrusted Garmin callback state', () => {
  registerGarminPassthroughAliases()
  cy.visit(
    '/settings/garmin-callback?code=e2e-invalid-code&state=e2e-untrusted-state',
  )
})

Then('the deployed backend should reject the Garmin callback state', () => {
  cy.wait('@garminStateRejection').then(({ request, response }) => {
    expectBearerAuthorization(request.headers)
    expect(response?.statusCode).to.equal(200)
    expect(response?.body?.data).to.equal(null)
    expect(response?.body?.errors).to.be.an('array').and.not.be.empty
    expect(
      response?.body?.errors.some((error: { message?: string }) =>
        error.message?.toLowerCase().includes('state'),
      ),
      'state rejection error',
    ).to.equal(true)
  })
  cy.get('[data-testid="garmin-callback-error"]', { timeout: 10000 })
    .should('be.visible')
    .and('contain.text', 'Garmin connection failed during completion')
})

Given('I visit Garmin callback with provider error', () => {
  registerGarminPassthroughAliases()
  cy.visit(
    '/settings/garmin-callback?error=access_denied&error_description=User%20cancelled&state=e2e-provider-error-state',
  )
})

Then('I should see a Garmin callback error', () => {
  cy.wait('@garminAuthorizationCancelled').then(({ request, response }) => {
    expectBearerAuthorization(request.headers)
    expect(response?.statusCode).to.equal(200)
    expect(response?.body?.errors).to.equal(undefined)
    expect(response?.body?.data?.cancelGarminAuthorization).to.equal(true)
  })
  cy.get('[data-testid="garmin-callback-error"]', { timeout: 10000 })
    .should('be.visible')
    .and('contain.text', 'Garmin sign-in was cancelled.')
})
