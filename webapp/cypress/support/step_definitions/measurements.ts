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

When("I use a mobile viewport", () => {
    cy.viewport(375, 667);
});

Then("I should see the mobile navigation", () => {
    cy.get('[aria-label="Go to dashboard"]').should("be.visible");
    cy.get('[aria-label="Open navigation menu"]')
        .should("be.visible")
        .and("have.attr", "aria-expanded", "false");
    cy.get('[aria-label="Primary navigation"]').should("not.be.visible");
});

When("I open the mobile navigation", () => {
    cy.get('[aria-label="Open navigation menu"]').click();
});

Then("I should see the open primary navigation", () => {
    cy.get('[aria-label="Open navigation menu"]')
        .should("have.attr", "aria-expanded", "true");
    cy.get('[aria-label="Primary navigation"]').should("be.visible");
});

When("I close the mobile navigation with Escape", () => {
    cy.get("body").trigger("keydown", { key: "Escape" });
});

Then("the mobile menu button should have focus", () => {
    cy.get('[aria-label="Open navigation menu"]')
        .should("have.attr", "aria-expanded", "false")
        .and("be.focused");
});

When("I choose Plans from the mobile navigation", () => {
    cy.get('[data-testid="nav-week-plans"]').click();
});

Then("I should be on the plans page with the mobile navigation closed", () => {
    cy.location("pathname").should("equal", "/plans");
    cy.get('[aria-label="Open navigation menu"]')
        .should("have.attr", "aria-expanded", "false");
    cy.get('[aria-label="Primary navigation"]').should("not.be.visible");
    cy.get(".main-content").should("be.focused");
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
