import { Given, When, Then } from "@badeball/cypress-cucumber-preprocessor";

When("I navigate to the recipes page", () => {
    cy.visit("/recipes");
});

Then("I should see the recipes page title", () => {
    cy.get('[data-testid="recipes-title"]', { timeout: 10000 })
        .should("be.visible")
        .and("contain.text", "Recipes");
});

When("I navigate to the new recipe page", () => {
    cy.visit("/recipes/new");
});

When("I fill in the recipe name with {string}", (value: string) => {
    cy.get('[data-testid="field-name"]').clear().type(value);
});

When("I fill in the recipe energy with {string}", (value: string) => {
    cy.get('[data-testid="field-energyKcal"]').clear().type(value);
});

Then("I should be redirected to the recipes list", () => {
    cy.get('[data-testid="save-btn"]', { timeout: 10000 }).should('not.be.disabled');
    cy.url({ timeout: 10000 }).should("match", /\/recipes$/);
});
