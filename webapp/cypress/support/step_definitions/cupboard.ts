import { Given, When, Then } from "@badeball/cypress-cucumber-preprocessor";
import { replaceInputValue, waitForFormReady } from "../form";

When("I navigate to the cupboard page", () => {
    cy.visit("/cupboard");
});

Then("I should see the cupboard page title", () => {
    cy.get('[data-testid="cupboard-title"]', { timeout: 10000 })
        .should("be.visible")
        .and("contain.text", "Cupboard");
});

When("I navigate to the add to cupboard page", () => {
    cy.visit("/cupboard/new");
    waitForFormReady();
});

Given("a food product exists named {string}", (name: string) => {
    // Navigate to products and create it via UI to ensure auth/context is correct
    cy.visit("/products/new");
    waitForFormReady();
    replaceInputValue('[data-testid="field-name"]', name, {force: true});
    replaceInputValue('[data-testid="field-size"]', '1000', {force: true});
    replaceInputValue('[data-testid="field-numServings"]', '4', {force: true});
    replaceInputValue('[data-testid="field-energyKcal"]', '500', {force: true});
    replaceInputValue('[data-testid="field-proteinG"]', '30', {force: true});
    replaceInputValue('[data-testid="field-fatG"]', '15', {force: true});
    replaceInputValue('[data-testid="field-carbsG"]', '50', {force: true});
    cy.get('[data-testid="field-carbsG"]').blur();
    cy.wait(100);
    cy.get('[data-testid="save-btn"]').click();
    cy.url().should("match", /\/products$/);
    cy.wait(2000); // Give backend/cache time to stabilize
});

When("I select {string} as the food item", (label: string) => {
    cy.get('[data-testid="field-foodId"] option', { timeout: 10000 })
        .should('contain.text', label)
        .contains(label)
        .invoke('val')
        .then((val) => {
            cy.get('[data-testid="field-foodId"]').select(val as string);
        });
});

Then("I should see {string} in the list", (text: string) => {
    cy.get('table').should('contain', text);
});

Then("I should be redirected to the cupboard list", () => {
    cy.get('[data-testid="save-btn"]', { timeout: 10000 }).should('not.be.disabled');
    cy.url({ timeout: 10000 }).should("match", /\/cupboard$/);
});
