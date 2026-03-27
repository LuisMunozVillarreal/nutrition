Feature: Exercises CRUD

  Scenario: View exercises list
    Given I am logged in
    When I navigate to the exercises page
    Then I should see the exercises page title

  Scenario: Create a new exercise
    Given I am logged in
    When I navigate to the new exercise page
    And I fill in the exercise day id with "1"
    And I select the exercise type "walk"
    And I fill in the exercise kcals with "200"
    And I click the save button
    Then I should be redirected to the exercises list
