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
