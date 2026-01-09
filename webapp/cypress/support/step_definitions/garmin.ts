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
    // Intercept with broad pattern to catch the request
    cy.intercept("POST", "*", (req) => {
        let body = req.body;
        if (typeof body === 'string') {
            try {
                body = JSON.parse(body);
            } catch (e) {
                // Not JSON, ignore
            }
        }

        // Check for operation name or query string
        if (body && (body.operationName === "ConnectGarmin" || (body.query && body.query.includes("mutation ConnectGarmin")))) {
            const redirectUri = body.variables ? body.variables.redirectUri : `${window.location.origin}/settings/garmin-callback`;

            req.reply({
                data: {
                    connectGarminUrl: redirectUri + "?code=testcode"
                }
            });
        }
    }).as("connectGarmin");

    cy.visit("/settings");
    cy.contains("Settings").should("be.visible");
});

When("I click {string}", (text: string) => {
    cy.wait(2000); // Wait for hydration
    cy.contains(text).click({ force: true });
});

Then("I should be redirected to the callback with code {string}", (code: string) => {
    // Verify we reached the callback page with expected code
    cy.url({ timeout: 15000 }).should("include", "/settings/garmin-callback");
    cy.url().should("include", `code=${code}`);
});

Then("I should see {string}", (text: string) => {
    // This checks for "Connected to Garmin"
    // The callback page mutation might take a second, so we use a generous timeout
    cy.contains(text, { timeout: 20000 }).should("be.visible");
});
