import { Given, When, Then } from "@badeball/cypress-cucumber-preprocessor";

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
});

Given("a food product exists named {string}", (name: string) => {
    // Navigate to products and create it via UI to ensure auth/context is correct
    cy.visit("/products/new");
    cy.get('[data-testid="field-name"]').type(name);
    cy.get('[data-testid="field-size"]').clear().type("1000");
    cy.get('[data-testid="field-numServings"]').clear().type("4");
    cy.get('[data-testid="field-energyKcal"]').clear().type("500");
    cy.get('[data-testid="field-proteinG"]').clear().type("30");
    cy.get('[data-testid="field-fatG"]').clear().type("15");
    cy.get('[data-testid="field-carbsG"]').clear().type("50");
    cy.get('[data-testid="save-btn"]').click();
    cy.url().should("match", /\/products$/);
    cy.wait(2000); // Give backend/cache time to stabilize
});

When("I select {string} as the food item", (label: string) => {
    cy.get('[data-testid="field-foodId"] option', { timeout: 10000 }).then($options => {
        const texts = [...$options].map(opt => opt.innerText);
        cy.log('Available options:', JSON.stringify(texts));
    });
    cy.get('[data-testid="field-foodId"] option', { timeout: 10000 }).should('contain', label);
    cy.get('[data-testid="field-foodId"]').select(label);
});

Then("I should see {string} in the list", (text: string) => {
    cy.get('table').should('contain', text);
});

Then("I should be redirected to the cupboard list", () => {
    cy.get('[data-testid="save-btn"]', { timeout: 10000 }).should('not.be.disabled');
    cy.url({ timeout: 10000 }).should("match", /\/cupboard$/);
});
