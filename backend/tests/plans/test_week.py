"""week plan tests module.

Weight = 90kg
body fat = 20%
BMR: 1925.2
Exercise rate = 1.375
Estimated TDEE = 2647.15
Deficit (kcals/day) = 300
Deficit distribution = 110, 110, 110, 110, 90, 80, 90

ECG110: Estimated Energy Goal w Deficit 110 = ETDEE - 300 * 1.1 = 2317.15
ECG90: Estimated Energy Goal w Deficit 90 = ETDEE - 300 * 0.9 = 2377.15
ECG80: Estimated Energy Goal w Deficit 80 = ETDEE - 300 * 0.8 = 2407.15

TDEE = 3000

CG110: Energy Goal w Deficit 110 = TDEE - 300 * 1.1 = 2670
CG90: Energy Goal w Deficit 90 = TDEE - 300 * 0.9 = 2730
CG80: Energy Goal w Deficit 80 = TDEE - 300 * 0.8 = 2760

Energy goal & intake
=====================
Energy goal would be the ETDEE if  energy intake

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
Energy intake < Energy goal

   1       2       3       4      5      6      7
ECG110  ECG110  ECG110  ECG110  ECG90  ECG80  ECG90

UC3:
----
Current day: 1
TDEE > ETDEE
Energy intake < Energy goal

  1       2       3       4      5      6      7
CG110  ECG110  ECG110  ECG110  ECG90  ECG80  ECG90

"""

from decimal import Decimal

import pytest

from apps.plans.models import Intake


def test_days_are_created(db, week_plan):
    """New week creates days correctly.

    Given A new week plan
     When The plan is created
     Then 7 days are created
      And Each day has a specific deficit distribution
    """
    # Then
    assert week_plan.days.count() == week_plan.PLAN_LENGTH_DAYS

    day_one = week_plan.days.all()[6]
    assert day_one.deficit == 180
    assert day_one.day_num == 1
    assert week_plan.days.all()[5].deficit == 160
    assert week_plan.days.all()[4].deficit == 180
    assert week_plan.days.all()[3].deficit == 220
    assert week_plan.days.all()[2].deficit == 220
    assert week_plan.days.all()[1].deficit == 220
    assert week_plan.days.all()[0].deficit == 220


def test_saving_week_doesnt_create_more_days(db, week_plan):
    """Save week doesn't create new days."""
    # When
    week_plan.save()

    # Then
    assert week_plan.days.count() == 7


@pytest.fixture
def zero_energy_kcal_goal(mocker):
    """Zero energy kcal goal mock."""
    return mocker.patch(
        "apps.plans.models.WeekPlan.energy_kcal_goal",
        new_callable=mocker.PropertyMock,
        return_value=Decimal("0"),
    )


def test_zero_energy_intake_perc(db, week_plan, zero_energy_kcal_goal):
    """Zero energy intake percentage works as expected."""
    assert week_plan.energy_kcal_intake_perc == 0


def test_new_week_not_completed(db, week_plan_factory):
    """New week is not completed."""
    # When a new week is created
    week = week_plan_factory()

    # Then the week doesn't appear as completed
    assert not week.completed


def test_week_completed(db, week_plan):
    """Week is completed when all its days are completed."""
    # When the days of a check are completed
    for day in week_plan.days.all():
        day.breakfast_exc = True
        day.lunch_exc = True
        day.snack_exc = True
        day.dinner_exc = True
        day.exercises_exc = True
        day.steps_exc = True
        day.save()

    # Then the week shows as completed
    week_plan.refresh_from_db()
    assert week_plan.completed


@pytest.fixture
def bmr_2000(mocker):
    """BMR mock."""
    return mocker.patch(
        "apps.measurements.models.Measurement.bmr",
        new_callable=mocker.PropertyMock,
        return_value=Decimal("2000"),
    )


def test_accumulated_consumed_energy(
    db, week_plan, bmr_2000, measurement, food_product_factory, intake_factory
):
    """Accumulated consumed energy is correct."""
    # pylint: disable=too-many-arguments,too-many-positional-arguments

    # Given a product
    food = food_product_factory(energy_kcal=2100)

    # And a serving from the product
    serving = food.servings.first()
    assert serving.energy_kcal == 2100

    # When the first day a serving from the product is consumed
    day = week_plan.days.all()[6]
    intake_factory(day=day, meal=Intake.MEAL_BREAKFAST, food=serving)

    # And the second day a serving from the product is consumed
    day = week_plan.days.all()[5]
    intake_factory(day=day, meal=Intake.MEAL_BREAKFAST, food=serving)

    # And the third day a serving from the product is consumed
    day = week_plan.days.all()[4]
    intake_factory(day=day, meal=Intake.MEAL_BREAKFAST, food=serving)

    # And the fourth day a serving from the product is consumed
    day = week_plan.days.all()[3]
    intake_factory(day=day, meal=Intake.MEAL_BREAKFAST, food=serving)

    # And the fifth day a serving from the product is consumed
    day = week_plan.days.all()[2]
    intake_factory(day=day, meal=Intake.MEAL_BREAKFAST, food=serving)

    # And the sixth day a serving from the product is consumed
    day = week_plan.days.all()[1]
    intake_factory(day=day, meal=Intake.MEAL_BREAKFAST, food=serving)

    # And the seventh day a serving from the product is consumed
    day = week_plan.days.all()[0]
    intake_factory(day=day, meal=Intake.MEAL_BREAKFAST, food=serving)

    # Then the first day has a surplus of 70 kcals
    day = week_plan.days.all()[6]
    assert day.tdee == 2210
    assert day.deficit == 180
    assert day.energy_kcal_goal == 2030
    assert day.energy_kcal == 2100
    assert day.energy_kcal_goal_diff == Decimal("-70")
    assert day.energy_kcal_goal_accumulated_diff == Decimal("-70")

    # And the second day has a surplus of 120 kcals
    day = week_plan.days.all()[5]
    assert day.energy_kcal_goal_diff == Decimal("-50")
    assert day.energy_kcal_goal_accumulated_diff == Decimal("-120")

    # And the third day has a surplus of 70 kcals
    day = week_plan.days.all()[4]
    assert day.energy_kcal_goal_diff == Decimal("-70")
    assert day.energy_kcal_goal_accumulated_diff == Decimal("-190")

    # And the fourth day has a surplus of 110 kcals
    day = week_plan.days.all()[3]
    assert day.energy_kcal_goal_diff == Decimal("-110")
    assert day.energy_kcal_goal_accumulated_diff == Decimal("-300")

    # And the fifth day has a surplus of 110 kcals
    day = week_plan.days.all()[2]
    assert day.energy_kcal_goal_diff == Decimal("-110")
    assert day.energy_kcal_goal_accumulated_diff == Decimal("-410")

    # And the sixth day has a surplus of 110 kcals
    day = week_plan.days.all()[1]
    assert day.energy_kcal_goal_diff == Decimal("-110")
    assert day.energy_kcal_goal_accumulated_diff == Decimal("-520")

    # And the seventh day has a surplus of 110 kcals
    day = week_plan.days.all()[0]
    assert day.energy_kcal_goal_diff == Decimal("-110")
    assert day.energy_kcal_goal_accumulated_diff == Decimal("-630")

    # And the weekly surplus is 630
    assert week_plan.energy_kcal_goal_diff == Decimal("-630")
