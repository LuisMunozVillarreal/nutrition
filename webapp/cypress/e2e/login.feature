Feature: User Login

  Scenario: Successful Login
    Given I am on the login page
    When I enter valid credentials
    And I click the sign in button
    Then I should be redirected to the home page
    And I should see a welcome message
