Feature: Garmin settings integration

  Scenario: Query and disconnect Garmin through the deployed backend
    Given I am logged in
    Given Garmin GraphQL requests use the deployed backend
    When I navigate to the settings page
    Then the deployed backend should report the seeded Garmin connection
    When I disconnect Garmin through the deployed backend
    Then the real Garmin disconnect should remain persisted

  Scenario: Reject an untrusted Garmin callback state in the deployed backend
    Given I am logged in
    Given I submit an untrusted Garmin callback state
    Then the deployed backend should reject the Garmin callback state

  Scenario: Handle Garmin provider error
    Given I am logged in
    When I visit Garmin callback with provider error
    Then I should see a Garmin callback error
