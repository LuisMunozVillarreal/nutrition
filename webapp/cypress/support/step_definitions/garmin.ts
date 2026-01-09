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
    cy.task("log", "--- STARTING SETTINGS PAGE STEP (DEBUG V3) ---");

    // Capture browser console logs safely
    cy.on("window:console", (msg) => {
        cy.task("log", `BROWSER_CONSOLE: ${msg.text()}`);
    });

    // Intercept with the broadest possible pattern
    cy.intercept({ method: "POST", url: "**" }, (req) => {
        cy.task("log", `INTERCEPTED: ${req.method} ${req.url}`);

        let body = req.body;
        if (typeof body === 'string') {
            try { body = JSON.parse(body); } catch (e) { }
        }

        if (body) {
            cy.task("log", `BODY_OP: ${body.operationName} | BODY_QUERY_MATCH: ${body.query && body.query.includes("mutation ConnectGarmin")}`);
        }

        if (body && (body.operationName === "ConnectGarmin" || (body.query && body.query.includes("mutation ConnectGarmin")))) {
            cy.task("log", "MATCHED ConnectGarmin mutation! Mocking response...");
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
    cy.task("log", `Attempting to click button: ${text}`);
    cy.wait(5000); // Wait for hydration

    cy.contains("button", text).should('be.visible').and('not.be.disabled').then($btn => {
        cy.task("log", `Button ready: ${$btn.text()}`);
    });

    cy.contains("button", text).click({ force: true });
    cy.task("log", "Click sent.");

    if (text === "Connect with Garmin") {
        cy.task("log", "Waiting for 'Redirecting...' state...");
        // Wait for state change to prove click was handled
        cy.contains("button", "Redirecting...", { timeout: 15000 }).should("be.visible");
        cy.task("log", "State changed successfully.");
    }
});

Then("I should be redirected to the callback with code {string}", (code: string) => {
    cy.task("log", `Waiting for redirect to include code=${code}`);
    cy.url({ timeout: 20000 }).should("include", "/settings/garmin-callback");
    cy.url().should("include", `code=${code}`);
});

Then("I should see {string}", (text: string) => {
    cy.task("log", `Looking for text: ${text}`);
    cy.contains(text, { timeout: 20000 }).should("be.visible");
});
