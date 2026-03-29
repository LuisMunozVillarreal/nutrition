import { Given, When, Then } from "@badeball/cypress-cucumber-preprocessor";

When("I navigate to the exercises page", () => {
    cy.visit("/exercises");
});

Then("I should see the exercises page title", () => {
    cy.get('[data-testid="exercises-title"]', { timeout: 10000 })
        .should("be.visible")
        .and("contain.text", "Exercises");
});

When("I navigate to the new exercise page", () => {
    cy.visit("/exercises/new");
});

When("I fill in the exercise day id with {string}", (value: string) => {
    cy.get('[data-testid="field-dayId"]').should('be.visible').clear({force: true}).type(value, {force: true});
});

When("I select the exercise type {string}", (value: string) => {
    cy.get('[data-testid="field-type"]').select(value);
});

When("I fill in the exercise kcals with {string}", (value: string) => {
    cy.get('[data-testid="field-kcals"]').should('be.visible').clear({force: true}).type(value, {force: true});
});

Then("I should be redirected to the exercises list", () => {
    cy.url({ timeout: 10000 }).should("include", "/exercises");
    cy.url().should("not.include", "/new");
});
