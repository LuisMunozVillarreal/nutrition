import { Given, Then } from '@badeball/cypress-cucumber-preprocessor'
import { listLayoutFixtures } from '../listLayoutFixtures'

const table = '[data-testid="data-table"]'

Given('the layout fixture for {string} at {int} pixels', (route: string, width: number) => {
  expect(listLayoutFixtures[route], 'known layout fixture').to.exist
  cy.viewport(width, 800)
  cy.intercept('GET', '**/api/auth/session', {
    user: { name: 'Layout test', email: 'layout@example.com', isStaff: true },
    expires: '2099-01-01T00:00:00Z', accessToken: 'layout-test-only',
  })
  cy.intercept('POST', '**/graphql/', { data: listLayoutFixtures[route] })
  cy.visit(`/${route}`)
  if (route.includes('/')) cy.get('[data-testid="form-ready"]').should('be.visible')
  cy.get(table).should('be.visible').find('tbody tr').should('have.length', 1)
})

Then('the list should stay within the page', () => {
  cy.document().should((doc) => {
    expect(doc.documentElement.scrollWidth, 'no global horizontal overflow')
      .to.be.at.most(doc.documentElement.clientWidth)
  })
  cy.get(table).parent().should(($container) => {
    const rect = $container[0].getBoundingClientRect()
    expect(rect.left, 'left edge').to.be.at.least(0)
    expect(rect.right, 'right edge').to.be.at.most($container[0].ownerDocument.documentElement.clientWidth)
  })
})

// CDP sends native touch input to Chromium, unlike trigger('touchmove') or scrollTo().
// Cypress scales the AUT iframe; transform local CSS coordinates into runner coordinates.
function swipeTable(direction: 'left' | 'right') {
  cy.get(table).parent().then({ timeout: 30000 }, async ($container) => {
    const element = $container[0].querySelector('table')!
    const win = element.ownerDocument.defaultView!
    win.scrollTo(0, win.scrollY + $container[0].getBoundingClientRect().top - 200)
    await new Promise(resolve => setTimeout(resolve, 100))
    const frame = window.parent.document.querySelector('iframe.aut-iframe')!
    const frameRect = frame.getBoundingClientRect()
    const scale = frameRect.width / win.innerWidth
    const container = element.parentElement!
    const rect = container.getBoundingClientRect()
    const x = frameRect.left + (rect.left + rect.width / 2) * scale
    const y = frameRect.top + (rect.top + rect.height / 2) * scale
    expect(element.ownerDocument.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)?.closest('table'), 'touch starts on the visible table').to.equal(element)
    return (async () => {
      const distance = (direction === 'left' ? -1 : 1) * rect.width * scale * 0.4
      for (let swipe = 0; swipe < Math.ceil(element.scrollWidth / Math.abs(distance)) + 2; swipe++) {
        for (let step = 0; step <= 10; step++) {
          await Cypress.automation('remote:debugger:protocol', {
            command: 'Input.dispatchTouchEvent',
            params: {
              type: step === 0 ? 'touchStart' : 'touchMove',
              touchPoints: [{ x: x + distance * step / 10, y }],
            },
          })
          await new Promise(resolve => setTimeout(resolve, 16))
        }
        await Cypress.automation('remote:debugger:protocol', {
          command: 'Input.dispatchTouchEvent', params: { type: 'touchEnd', touchPoints: [] },
        })
      }
    })()
  })
}

Then('a touch swipe should reveal the last column and return to the first', () => {
  cy.get(table).parent().should(($container) => {
    const container = $container[0]
    expect(container.scrollWidth, 'table needs local scrolling').to.be.greaterThan(container.clientWidth)
    expect(container.ownerDocument.defaultView!.getComputedStyle(container).overflowX,
      'overflow accepts user scrolling').to.equal('auto')
    expect(container.scrollLeft, 'starts at first column').to.equal(0)
  })
  swipeTable('left')
  cy.get(table).parent().should(($container) => {
    const container = $container[0]
    expect(container.scrollLeft, 'native touch moved the table').to.be.greaterThan(0)
    const cell = container.querySelector('tbody tr td:last-child')!.getBoundingClientRect()
    expect(cell.right, 'last column is reachable').to.be.at.most(container.getBoundingClientRect().right + 1)
  })
  swipeTable('right')
  cy.get(table).parent().should('have.prop', 'scrollLeft', 0)
  cy.location('pathname').should('not.match', /\/new$/)
  cy.document().should((doc) => {
    expect(doc.documentElement.scrollLeft, 'only the table scrolled').to.equal(0)
  })
})

Then('the desktop list should show every column without scrolling', () => {
  cy.get('.sidebar').should('be.visible')
  cy.get('.mobile-header').should('not.be.visible')
  cy.get(table).parent().should(($container) => {
    const container = $container[0]
    expect(container.scrollWidth).to.equal(container.clientWidth)
  })
  cy.get(table).find('th').first().click().find('svg').should('be.visible')
})
