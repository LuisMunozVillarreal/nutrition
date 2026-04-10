import { Given, When, Then } from "@badeball/cypress-cucumber-preprocessor";

Given("I am logged in", () => {
    // Use the known test user credentials
    cy.visit("/login");
    cy.get('input[type="email"]').type("user@example.com");
    cy.get('input[type="password"]').type("password123");
    cy.get('button[type="submit"]').click();

    // Check that we're on the dashboard or home page
    cy.url({ timeout: 15000 }).should("not.include", "/login");
    
    // Ensure the session is loaded in the browser state
    cy.get('body').should('be.visible');
});

When("I navigate to the measurements page", () => {
    cy.visit("/measurements");
});

Then("I should see the measurements page title", () => {
    cy.get('[data-testid="measurements-title"]', { timeout: 10000 })
        .should("be.visible")
        .and("contain.text", "Measurements");
});

When("I navigate to the new measurement page", () => {
    cy.visit("/measurements/new");
});

When("I fill in the body fat percentage with {string}", (value: string) => {
    cy.get('[data-testid="field-bodyFatPerc"]').clear();
    cy.get('[data-testid="field-bodyFatPerc"]').type(value);
});

When("I fill in the weight with {string}", (value: string) => {
    cy.get('[data-testid="field-weight"]').clear();
    cy.get('[data-testid="field-weight"]').type(value);
    cy.wait(100); // Give React concurrent mode time to update state
});

When("I click the save button", () => {
    cy.get('[data-testid="save-btn"]').click();
});

Then("I should be redirected to the measurements list", () => {
    // Assert there's NO error toast, and wait a bit for it
    cy.get('body').then($body => {
        if ($body.find('[data-testid="form-error"]').length > 0) {
            throw new Error("Form Error: " + $body.find('[data-testid="form-error"]').text().trim());
        }
    });
    cy.url({ timeout: 10000 }).should("not.include", "/new").then(() => {
        cy.get('body').then($body => {
            if ($body.find('[data-testid="form-error"]').length > 0) {
                throw new Error("Form Error: " + $body.find('[data-testid="form-error"]').text().trim());
            }
        });
    });
});
