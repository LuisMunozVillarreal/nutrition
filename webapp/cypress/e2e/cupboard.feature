Feature: Cupboard CRUD

  Scenario: View cupboard list
    Given I am logged in
    When I navigate to the cupboard page
    Then I should see the cupboard page title

  Scenario: Add an item to the cupboard
    Given I am logged in
    And a food product exists named "Cypress Milk TEST"
    When I navigate to the add to cupboard page
    And I select "Product: Cypress Milk TEST" as the food item
    And I click the save button
    Then I should be redirected to the cupboard list
    And I should see "Cypress Milk TEST" in the list
