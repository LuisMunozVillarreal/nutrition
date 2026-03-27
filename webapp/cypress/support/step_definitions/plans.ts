import { Given, When, Then } from "@badeball/cypress-cucumber-preprocessor";

When("I navigate to the week plans page", () => {
    cy.visit("/plans");
});

Then("I should see the week plans page title", () => {
    cy.get('[data-testid="plans-title"]', { timeout: 10000 })
        .should("be.visible")
        .and("contain.text", "Week Plans");
});

When("I navigate to the days page", () => {
    cy.visit("/days");
});

Then("I should see the days page title", () => {
    cy.get('[data-testid="days-title"]', { timeout: 10000 })
        .should("be.visible")
        .and("contain.text", "Days");
});
