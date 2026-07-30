import { Given, When, Then } from '@badeball/cypress-cucumber-preprocessor'
import { e2eCredentials } from '../e2eCredentials'

Given('I am on the login page', () => {
  cy.visit('/login')
})

When('I enter valid credentials', () => {
  const { email, password } = e2eCredentials('regular')
  cy.get('input[type="email"]').type(email, { log: false })
  cy.get('input[type="password"]').type(password, { log: false })
})

When('I click the sign in button', () => {
  cy.get('button[type="submit"]').click()
})

Then('I should be redirected to the home page', () => {
  cy.on('window:alert', (message) => {
    expect(message).to.not.equal('Login failed')
  })

  const expectedUrl = `${Cypress.config().baseUrl?.replace(/\/$/, '')}/`
  cy.url({ timeout: 20000 }).should((url) => {
    expect(`${url.replace(/\/$/, '')}/`).to.equal(expectedUrl)
  })
})

Then('I should see a welcome message', () => {
  cy.get('body', { timeout: 10000 }).should('exist')
  cy.get('body').then(($body) => {
    const bodyText = $body.text()
    const hasDashboard =
      bodyText.includes('Time to dominate') ||
      bodyText.includes('Your daily metrics') ||
      bodyText.includes('Current Weight') ||
      bodyText.includes('Body Composition')

    expect(hasDashboard, 'Dashboard content should be visible').to.be.true
  })
})
