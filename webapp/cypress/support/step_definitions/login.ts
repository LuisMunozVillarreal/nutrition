import { Given, When, Then } from "@badeball/cypress-cucumber-preprocessor";

Given("I am on the login page", () => {
    cy.visit("/login");
});

When("I enter valid credentials", () => {
    // We assume backend has a user with these credentials or we mock it.
    // For integration test, we should ensure this user exists or seed it.
    // Here we use a known test user if available, or just mock the network response if we only test frontend functionality.
    // Since task is Integration, we should use real backend.
    // But backend is empty. I should use `db_seeds` or create user manually.
    // I'll assume a user user@example.com / password exists or I'll create it via task.

    // For now, let's type dummy credentials that mapped to what I'll seed.
    cy.get('input[type="email"]').type("user@example.com");
    cy.get('input[type="password"]').type("password123");
});

When("I click the sign in button", () => {
    cy.get('button[type="submit"]').click();
});

Then("I should be redirected to the home page", () => {
    cy.url().should("eq", Cypress.config().baseUrl + "/");
});

Then("I should see a welcome message", () => {
    // Log current URL for debugging
    cy.url().then(url => cy.log(`Current URL: ${url}`));

    // Wait for page to be fully loaded
    cy.get('body', { timeout: 10000 }).should('exist');

    // Log the page HTML for debugging
    cy.document().then(doc => {
        cy.log(`Page title: ${doc.title}`);
        cy.log(`Body contains: ${doc.body.innerText.substring(0, 200)}`);
    });

    // Check if we're on the home page
    cy.url().should('eq', Cypress.config().baseUrl + '/');

    // Wait for any potential client-side navigation or auth checks
    cy.wait(2000);

    // Try to find the greeting element with detailed logging
    cy.get('[data-testid="dashboard-greeting"]', { timeout: 20000 })
        .should('exist')
        .should('be.visible')
        .then($el => {
            cy.log(`Greeting text found: ${$el.text()}`);
        })
        .and('contain', 'Time to dominate');
});
