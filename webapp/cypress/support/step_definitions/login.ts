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
    cy.contains("Ready to crush it");
});
