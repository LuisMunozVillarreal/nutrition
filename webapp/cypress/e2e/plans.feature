Feature: Plans, Days, and Intakes

  Scenario: View week plans list
    Given I am logged in
    When I navigate to the week plans page
    Then I should see the week plans page title

  Scenario: View days list
    Given I am logged in
    When I navigate to the days page
    Then I should see the days page title

  # Intakes are usually managed inside the Day screen,
  # but testing the stubs and logic is still useful.
