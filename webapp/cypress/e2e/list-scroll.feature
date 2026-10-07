Feature: Reach every column without widening the page
  # Network fixtures isolate layout from authentication and backend availability.
  Scenario Outline: Scroll a populated list on a narrow phone
    Given the layout fixture for "<route>" at <width> pixels
    Then the list should stay within the page
    And a touch swipe should reveal the last column and return to the first

    Examples:
      | route        | width |
      | products     | 280   |
      | products     | 320   |
      | products     | 360   |
      | recipes      | 280   |
      | recipes      | 320   |
      | recipes      | 360   |
      | cupboard     | 280   |
      | cupboard     | 320   |
      | cupboard     | 360   |
      | measurements | 280   |
      | measurements | 320   |
      | measurements | 360   |
      | goals        | 280   |
      | goals        | 320   |
      | goals        | 360   |
      | plans        | 280   |
      | plans        | 320   |
      | plans        | 360   |
      | days         | 280   |
      | days         | 320   |
      | days         | 360   |
      | exercises    | 280   |
      | exercises    | 320   |
      | exercises    | 360   |
      | steps        | 280   |
      | steps        | 320   |
      | steps        | 360   |
      | plans/1      | 280   |
      | plans/1      | 320   |
      | plans/1      | 360   |
      | days/1       | 280   |
      | days/1       | 320   |
      | days/1       | 360   |
      | products/1   | 280   |
      | products/1   | 320   |
      | products/1   | 360   |
      | recipes/1    | 280   |
      | recipes/1    | 320   |
      | recipes/1    | 360   |

  Scenario Outline: Keep the desktop list layout
    Given the layout fixture for "<route>" at 1440 pixels
    Then the list should stay within the page
    And the desktop list should show every column without scrolling

    Examples:
      | route        |
      | products     |
      | recipes      |
      | cupboard     |
      | measurements |
      | goals        |
      | plans        |
      | days         |
      | exercises    |
      | steps        |
      | plans/1      |
      | days/1       |
      | products/1   |
      | recipes/1    |
