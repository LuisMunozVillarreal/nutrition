import { Given, When, Then } from "@badeball/cypress-cucumber-preprocessor";

When("I navigate to the exercises page", () => {
    cy.visit("/exercises");
});

Then("I should see the exercises page title", () => {
    cy.get('[data-testid="exercises-title"]', { timeout: 10000 })
        .should("be.visible")
        .and("contain.text", "Exercises");
});

When("I navigate to the new exercise page", () => {
    cy.visit("/exercises/new");
});

let validDayId = "1";

Given("a day exists for the exercise", () => {
    // We execute the python script to ensure the DB state is valid for testing
    cy.exec('cd ../backend && uv run python seed_test_day.py', { failOnNonZeroExit: true })
      .then((result) => {
          if (result.stdout) {
              const lines = result.stdout.split("\n");
              validDayId = lines[lines.length - 1].trim() || "1";
          }
      });
});

When("I fill in the exercise day id with the valid day ID", () => {
    cy.get('[data-testid="field-dayId"]').should('be.visible').clear({force: true});
    cy.get('[data-testid="field-dayId"]').type(validDayId, {force: true});
});



When("I select the exercise type {string}", (value: string) => {
    cy.get('[data-testid="field-type"]').select(value);
});

When("I fill in the exercise kcals with {string}", (value: string) => {
    cy.get('[data-testid="field-kcals"]').should('be.visible').clear({force: true});
    cy.get('[data-testid="field-kcals"]').type(value, {force: true});
    cy.wait(100);
});

Then("I should be redirected to the exercises list", () => {
    cy.get('body').then($body => {
        if ($body.find('[data-testid="form-error"]').length > 0) {
            throw new Error("Form Error: " + $body.find('[data-testid="form-error"]').text().trim());
        }
    });
    cy.url({ timeout: 10000 }).should("not.include", "/new");
});
