import { When, Then } from "@badeball/cypress-cucumber-preprocessor";
import { e2eFixtureName } from "../e2eFixtures";

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
    cy.get('[data-testid="field-name"]').should('be.visible').clear({force: true});
    cy.get('[data-testid="field-name"]').type(e2eFixtureName(value), {force: true});
    cy.wait(100);
});

When("I fill in the recipe energy with {string}", (value: string) => {
    cy.get('[data-testid="field-energyKcal"]').should('be.visible').clear({force: true});
    cy.get('[data-testid="field-energyKcal"]').type(value, {force: true});
    cy.wait(100);
});

Then("I should be redirected to the recipes list", () => {
    cy.url({ timeout: 10000 }).should("match", /\/recipes$/);
    cy.get('[data-testid="recipes-title"]', { timeout: 10000 }).should(
        "be.visible",
    );
});
