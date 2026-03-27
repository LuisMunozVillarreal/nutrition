import { Given, When, Then } from "@badeball/cypress-cucumber-preprocessor";

Given("I am logged in", () => {
    // Use the known test user credentials
    cy.visit("/login");
    cy.get('input[type="email"]').type("user@example.com");
    cy.get('input[type="password"]').type("password123");
    cy.get('button[type="submit"]').click();
    cy.wait(5000);
    cy.url().should("not.include", "/login");
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
    cy.get('[data-testid="field-bodyFatPerc"]').clear().type(value);
});

When("I fill in the weight with {string}", (value: string) => {
    cy.get('[data-testid="field-weight"]').clear().type(value);
});

When("I click the save button", () => {
    cy.get('[data-testid="save-btn"]').click();
});

Then("I should be redirected to the measurements list", () => {
    cy.url({ timeout: 10000 }).should("include", "/measurements");
    cy.url().should("not.include", "/new");
});
