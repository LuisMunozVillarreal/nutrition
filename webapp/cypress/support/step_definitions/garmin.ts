import { Given, When, Then } from "@badeball/cypress-cucumber-preprocessor";

Given("I am logged in", () => {
    cy.visit("/login");
    cy.get('input[name="email"]').type("user@example.com");
    cy.get('input[name="password"]').type("password123");
    cy.get('button[type="submit"]').click();
    // Wait for redirect to home or welcome message
    cy.contains("Welcome", { timeout: 15000 }).should("be.visible");
});

Given("I visit the settings page", () => {
    // Intercept ConnectGarmin mutation to avoid actual Garmin redirect in tests
    cy.intercept("POST", "**/graphql/", (req) => {
        const body = req.body;
        if (body && (body.operationName === "ConnectGarmin" || (body.query && body.query.includes("mutation ConnectGarmin")))) {
            const redirectUri = body.variables?.redirectUri || `${window.location.origin}/settings/garmin-callback`;
            req.reply({
                data: {
                    connectGarminUrl: `${redirectUri}?code=testcode`
                }
            });
        }
    }).as("connectGarmin");

    cy.visit("/settings");
    cy.contains("Settings").should("be.visible");
});

When("I click {string}", (text: string) => {
    cy.contains("button", text).click();
});

Then("I should be redirected to the callback with code {string}", (code: string) => {
    cy.url({ timeout: 20000 }).should("include", "/settings/garmin-callback");
    cy.url().should("include", `code=${code}`);
});

Then("I should see {string}", (text: string) => {
    cy.contains(text, { timeout: 20000 }).should("be.visible");
});
