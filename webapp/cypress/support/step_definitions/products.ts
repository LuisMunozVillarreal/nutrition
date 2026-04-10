import { Given, When, Then } from "@badeball/cypress-cucumber-preprocessor";

When("I navigate to the products page", () => {
    cy.visit("/products");
});

Then("I should see the products page title", () => {
    cy.get('[data-testid="products-title"]', { timeout: 10000 })
        .should("be.visible")
        .and("contain.text", "Food Products");
});

When("I navigate to the new product page", () => {
    cy.visit("/products/new");
});

When("I fill in the product name with {string}", (value: string) => {
    cy.get('[data-testid="field-name"]').should('be.visible').clear({force: true});
    cy.get('[data-testid="field-name"]').type(value, {force: true});
    cy.wait(100);
});

When("I fill in the product energy with {string}", (value: string) => {
    cy.get('[data-testid="field-energyKcal"]').should('be.visible').clear({force: true});
    cy.get('[data-testid="field-energyKcal"]').type(value, {force: true});
    cy.wait(100);
});

Then("I should be redirected to the products list", () => {
    cy.get('[data-testid="save-btn"]', { timeout: 10000 }).should('not.be.disabled');
    cy.get('body').then($body => {
        if ($body.find('.toast-error').length > 0) {
            throw new Error('API SAVE ERROR: ' + $body.find('.toast-error').text());
        }
    });
    cy.url({ timeout: 10000 }).should("match", /\/products$/);
});
