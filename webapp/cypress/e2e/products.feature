Feature: Food Products CRUD

  Scenario: View food products list
    Given I am logged in
    When I navigate to the products page
    Then I should see the products page title

  Scenario: Create a new food product
    Given I am logged in
    When I navigate to the new product page
    And I fill in the product name with "Oats"
    And I fill in the product energy with "370"
    And I click the save button
    Then I should be redirected to the products list
