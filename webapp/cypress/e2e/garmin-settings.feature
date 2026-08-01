Feature: Garmin settings integration

  Scenario: View Garmin disconnected state
    Given I am logged in
    Given Garmin integration is disconnected
    When I navigate to the settings page
    Then I should see the settings page title
    And I should see Garmin as disconnected

  Scenario: Complete Garmin OAuth callback
    Given I am logged in
    Given Garmin integration is disconnected
    When I navigate to the settings page
    And I mock Garmin OAuth begin response with local callback URL
    And I click the Garmin connect button
    Then I should be redirected to the Garmin callback page
    Then I should return to the settings page after successful Garmin callback

  Scenario: Disconnect Garmin from settings
    Given I am logged in
    Given Garmin integration is connected
    When I navigate to the settings page
    And I click the Garmin disconnect button
    Then I should see Garmin as disconnected

  Scenario: Handle Garmin provider error
    Given I am logged in
    When I visit Garmin callback with provider error
    Then I should see a Garmin callback error
