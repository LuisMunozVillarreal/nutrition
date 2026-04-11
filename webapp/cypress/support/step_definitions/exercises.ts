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

Given("a day exists for the exercise", () => {
    // Try local Python script first (dev environment).
    // In CI, the seed is done as a setup step, so this may fail — we then
    // query the GraphQL API to get the day ID.
    cy.exec('cd ../backend && .venv/bin/python scripts/seed_test_day.py', { failOnNonZeroExit: false })
      .then((result) => {
          if ((result.code === 0 || result.exitCode === 0) && result.stdout) {
              const lines = result.stdout.trim().split("\n");
              const id = lines[lines.length - 1].trim() || "1";
              cy.wrap(id).as('validDayId');
          } else {
              // Fallback: query GraphQL API for the first day ID
              cy.request({
                  method: 'POST',
                  url: '/graphql/',
                  body: {
                      query: '{ weekPlans { days { id } } }'
                  },
                  headers: { 'Content-Type': 'application/json' },
              }).then((resp) => {
                  const plans = resp.body?.data?.weekPlans;
                  if (plans && plans.length > 0 && plans[0].days?.length > 0) {
                      cy.wrap(String(plans[0].days[0].id)).as('validDayId');
                  } else {
                      throw new Error("Could not find any days via Python or GraphQL! Python script result: " + JSON.stringify(result));
                  }
              });
          }
      });
});

When("I fill in the exercise day id with the valid day ID", () => {
    cy.get('[data-testid="field-dayId"]').should('be.visible').clear({force: true});
    cy.get('@validDayId').then((dayId) => {
        cy.log("RESOLVED DAY ID: " + dayId);
        cy.get('[data-testid="field-dayId"]').type(String(dayId), {force: true});
    });
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
