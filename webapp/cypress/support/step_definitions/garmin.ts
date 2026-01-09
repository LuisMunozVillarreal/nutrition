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
    cy.task("log", "--- STARTING SETTINGS PAGE STEP (DEBUG V4) ---");

    // Capture browser console logs
    cy.on("window:console", (msg) => {
        cy.task("log", `BROWSER_CONSOLE: ${msg.type()} | ${msg.text()}`);
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

    // Verify console listener is working
    cy.window().then((win) => {
        win.console.log("CYPRESS_CONSOLE_LISTENER_VERIFICATION");
    });
});

When("I click {string}", (text: string) => {
    cy.task("log", `Attempting to click button: ${text}`);
    cy.wait(5000); // Initial wait for hydration

    if (text === "Connect with Garmin") {
        const attemptClick = (attempts = 0) => {
            if (attempts > 10) {
                cy.task("log", "CRITICAL: Click loop timed out!");
                return;
            }

            cy.task("log", `Click attempt ${attempts + 1}...`);
            cy.contains("button", text).click({ force: true });

            // Check if state changed
            cy.wait(2000);
            cy.get('body').then(($body) => {
                if ($body.text().includes("Redirecting...")) {
                    cy.task("log", "Success! Found 'Redirecting...' text.");
                } else {
                    cy.task("log", "Still no 'Redirecting...' text, retrying click...");
                    attemptClick(attempts + 1);
                }
            });
        };
        attemptClick();
    } else {
        cy.contains("button", text).click({ force: true });
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
