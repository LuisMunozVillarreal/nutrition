"""week plan tests module.

Weight = 90kg
body fat = 20%
BMR: 1925.2
Exercise rate = 1.375
Estimated TDEE = 2647.15
Deficit (kcals/day) = 300
Deficit distribution = 110, 110, 110, 110, 90, 80, 90

ECG110: Estimated Calorie Goal w Deficit 110 = ETDEE - 300 * 1.1 = 2317.15
ECG90: Estimated Calorie Goal w Deficit 90 = ETDEE - 300 * 0.9 = 2377.15
ECG80: Estimated Calorie Goal w Deficit 80 = ETDEE - 300 * 0.8 = 2407.15

TDEE = 3000

CG110: Calorie Goal w Deficit 110 = TDEE - 300 * 1.1 = 2670
CG90: Calorie Goal w Deficit 90 = TDEE - 300 * 0.9 = 2730
CG80: Calorie Goal w Deficit 80 = TDEE - 300 * 0.8 = 2760

Calorie goal & intake
=====================
Calorie goal would be the ETDEE if  calorie intake

Use cases
=========

UC1:
----
Current day: 0

   1       2       3       4      5      6      7
ECG110  ECG110  ECG110  ECG110  ECG90  ECG80  ECG90

UC2:
----
Current day 1
TDEE < ETDEE
Calorie intake < Calorie goal

   1       2       3       4      5      6      7
ECG110  ECG110  ECG110  ECG110  ECG90  ECG80  ECG90
UC3:
----
Current day: 1
TDEE > ETDEE
Calorie intake < Calorie goal

  1       2       3       4      5      6      7
CG110  ECG110  ECG110  ECG110  ECG90  ECG80  ECG90

"""

from decimal import Decimal

import pytest


def test_days_are_created(db, week_plan):
    """New week creates days correctly.

    Given A new week plan
     When The plan is created
     Then 7 days are created
      And Each day has a specific deficit distribution
    """
    # Then
    assert week_plan.days.count() == week_plan.PLAN_LENGTH_DAYS

    day_one = week_plan.days.all()[0]
    assert day_one.deficit == 180
    assert day_one.day_num == 1
    assert week_plan.days.all()[1].deficit == 160
    assert week_plan.days.all()[2].deficit == 180
    assert week_plan.days.all()[3].deficit == 220
    assert week_plan.days.all()[4].deficit == 220
    assert week_plan.days.all()[5].deficit == 220
    assert week_plan.days.all()[6].deficit == 220


def test_saving_week_doesnt_create_more_days(db, week_plan):
    """Save week doesn't create new days."""
    # When
    week_plan.save()

    # Then
    assert week_plan.days.count() == 7


def test_calorie_goal_with_surplus(db, week_plan, intake_factory, serving):
    """Calorie goal with surplus is correct."""
    # Given
    day_one = week_plan.days.all()[0]
    day_one.tracked = True
    day_one.save()
    for _ in range(30):
        intake_factory(day=day_one, food=serving)

    day_two = week_plan.days.all()[1]
    day_two.tracked = True
    day_two.save()
    for _ in range(30):
        intake_factory(day=day_two, food=serving)

    day_three = week_plan.days.all()[2]

    # When / Then
    assert day_three.plan.extra_surplus(day_three.day_num) == Decimal(
        "508.612"
    )


@pytest.fixture
def zero_calorie_goal(mocker):
    """Zero calorie goal mock."""
    return mocker.patch(
        "apps.plans.models.WeekPlan.calorie_goal",
        new_callable=mocker.PropertyMock,
        return_value=Decimal("0"),
    )


def test_zero_calorie_intake_perc(db, week_plan, zero_calorie_goal):
    """Zero calorie intake percentage works as expected."""
    assert week_plan.calorie_intake_perc == 0
