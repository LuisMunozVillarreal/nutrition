Feature: Measurements CRUD

  Scenario: View measurements list
    Given I am logged in
    When I navigate to the measurements page
    Then I should see the measurements page title

  Scenario: Create a new measurement
    Given I am logged in
    When I navigate to the new measurement page
    And I fill in the body fat percentage with "20.5"
    And I fill in the weight with "82.0"
    And I click the save button
    Then I should be redirected to the measurements list

  Scenario: Navigate away from measurements on a phone
    Given I am logged in
    And I use a mobile viewport
    When I navigate to the measurements page
    Then I should see the mobile navigation
    When I open the mobile navigation
    Then I should see the open primary navigation
    When I close the mobile navigation with Escape
    Then the mobile menu button should have focus
    When I open the mobile navigation
    And I choose Plans from the mobile navigation
    Then I should be on the plans page with the mobile navigation closed
