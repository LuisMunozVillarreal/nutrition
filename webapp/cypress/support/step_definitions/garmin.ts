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
    cy.task("log", "--- STARTING SETTINGS PAGE STEP (DEBUG V2) ---");

    // Capture browser console logs more aggressively
    cy.on("window:before:load", (win) => {
        cy.task("log", "Window before load - attaching console listeners");
        const originalLog = win.console.log;
        win.console.log = (...args) => {
            cy.task("log", `BROWSER_LOG: ${args.map(a => typeof a === 'object' ? JSON.stringify(a) : a).join(' ')}`);
            originalLog.apply(win.console, args);
        };
        const originalError = win.console.error;
        win.console.error = (...args) => {
            cy.task("log", `BROWSER_ERROR: ${args.map(a => typeof a === 'object' ? JSON.stringify(a) : a).join(' ')}`);
            originalError.apply(win.console, args);
        };
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
    cy.wait(4000); // Increase wait for hydration

    cy.contains("button", text).should('be.visible').then($btn => {
        cy.task("log", `Button state: ${$btn.text()}, disabled: ${$btn.prop('disabled')}`);
    });

    // Click and expect state change if it's the connect button
    cy.contains("button", text).click({ force: true });
    cy.task("log", "Click sent.");

    if (text === "Connect with Garmin") {
        cy.task("log", "Waiting for 'Redirecting...' state...");
        // This will fail the test early if the click was a "dead click"
        cy.contains("button", "Redirecting...", { timeout: 10000 }).should("be.visible");
        cy.task("log", "State changed to 'Redirecting...'. All good.");
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
```
