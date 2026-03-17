// Import commands.js using ES2015 syntax:
import './commands'

Cypress.on('window:before:load', (win) => {
  cy.spy(win.console, 'error').as('consoleError')
  cy.spy(win.console, 'log').as('consoleLog')
  cy.spy(win.console, 'warn').as('consoleWarn')
})

afterEach(() => {
  cy.get('@consoleError', { log: false }).then((spy: any) => {
    if (spy.getCalls) {
      for (const call of spy.getCalls()) {
        cy.task('log', `CONSOLE ERROR: ${call.args.join(' ')}`, { log: false })
      }
    }
  })
  
  cy.get('@consoleWarn', { log: false }).then((spy: any) => {
    if (spy.getCalls) {
      for (const call of spy.getCalls()) {
        cy.task('log', `CONSOLE WARN: ${call.args.join(' ')}`, { log: false })
      }
    }
  })
})
