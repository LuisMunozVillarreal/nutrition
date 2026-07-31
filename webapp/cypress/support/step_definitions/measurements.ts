import { When, Then } from "@badeball/cypress-cucumber-preprocessor";
import { replaceInputValue, waitForFormReady } from "../form";

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
    waitForFormReady();
});

When("I fill in the body fat percentage with {string}", (value: string) => {
    cy.wrap(String(Number.parseFloat(value))).as('createdBodyFatPerc');
    replaceInputValue('[data-testid="field-bodyFatPerc"]', value);
});

When("I fill in the weight with {string}", (value: string) => {
    cy.wrap(String(Number.parseFloat(value))).as('createdWeight');
    replaceInputValue('[data-testid="field-weight"]', value);
    cy.wait(100); // Give React concurrent mode time to update state
});

When("I click the save button", () => {
    cy.get('[data-testid="save-btn"]').click();
});

Then("I should be redirected to the measurements list", () => {
    cy.location('pathname', { timeout: 20000 }).should('equal', '/measurements');
    cy.get('[data-testid="measurements-title"]', { timeout: 10000 })
        .should('be.visible')
        .and('contain.text', 'Measurements');
    cy.get('@createdBodyFatPerc').then((bodyFatPerc) => {
        cy.get('@createdWeight').then((weight) => {
            cy.contains('tr', String(bodyFatPerc), { timeout: 10000 })
                .should('contain.text', String(weight));
        });
    });
});
