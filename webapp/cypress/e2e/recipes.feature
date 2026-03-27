Feature: Recipes CRUD

  Scenario: View recipes list
    Given I am logged in
    When I navigate to the recipes page
    Then I should see the recipes page title

  Scenario: Create a new recipe
    Given I am logged in
    When I navigate to the new recipe page
    And I fill in the recipe name with "Omelette"
    And I fill in the recipe energy with "250"
    And I click the save button
    Then I should be redirected to the recipes list
