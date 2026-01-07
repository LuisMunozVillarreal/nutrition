Feature: Garmin Integration

  Scenario: Connect Garmin Account
    Given I am logged in
    And I visit the settings page
    When I click "Connect with Garmin"
    Then I should be redirected to the callback with code "testcode"
    And I should see "Connected to Garmin"
