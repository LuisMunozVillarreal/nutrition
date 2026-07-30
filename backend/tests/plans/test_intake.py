"""Intake tests."""

from decimal import Decimal


def test_no_food_intake(day, intake_factory):
    """No food intake doesn't add nutrients to the day."""
    # Given a day with no intakes
    assert day.intakes.count() == 0

    # When an intake is created with no food
    intake_factory(food=None, day=day)

    # Then the day gets an intake
    assert day.intakes.count() == 1

    # And the day doesn't get its nutrients increased
    assert day.energy_kcal == 0


def test_custom_intake_updates_day_nutrients(day, intake_factory):
    """A foodless intake with direct nutrients updates day rollups."""
    intake = intake_factory(
        food=None,
        day=day,
        energy_kcal=Decimal("400"),
        protein_g=Decimal("30"),
    )

    day.refresh_from_db()
    assert intake.processed is True
    assert day.energy_kcal == Decimal("400.00")
    assert day.protein_g == Decimal("30.00")

    intake.energy_kcal = Decimal("250")
    intake.protein_g = Decimal("20")
    intake.save()

    day.refresh_from_db()
    assert day.energy_kcal == Decimal("250.00")
    assert day.protein_g == Decimal("20.00")


def test_delete_custom_intake_decreases_day_nutrients(day, intake_factory):
    """Deleting a foodless custom intake removes its day rollup values."""
    intake = intake_factory(
        food=None,
        day=day,
        energy_kcal=Decimal("400"),
        protein_g=Decimal("30"),
    )

    intake.delete()

    day.refresh_from_db()
    assert day.energy_kcal == Decimal("0.00")
    assert day.protein_g == Decimal("0.00")


def test_add_food_to_existing_intake(intake_factory, serving):
    """Adding food to an existing intake increases the day's nutrients."""
    # Given an intake with no food
    intake = intake_factory(food=None)

    # When a food is added to the intake
    intake.food = serving
    intake.save()

    # Then the day gets its nutrients increased
    intake.day.refresh_from_db()
    assert intake.day.energy_kcal == 106


def test_remove_food_from_existing_intake(intake):
    """Removing food from an existing intake decreases the day's nutrients."""
    # When a food is removed from the intake
    intake.food = None
    intake.save()

    # Then the day gets its nutrients decreased
    intake.day.refresh_from_db()
    assert intake.day.energy_kcal == 0


def test_delete_intake_with_food(intake):
    """Deleting an intake decreases the day's nutrients."""
    # Given a day with some energy consumed
    assert intake.day.energy_kcal == 106

    # When the intake with food is deleted
    intake.delete()

    # Then the day gets its nutrients decreased
    intake.day.refresh_from_db()
    assert intake.day.energy_kcal == 0


def test_delete_intake_without_food(intake_factory):
    """Deleting an intake without food doesn't decrease the day's nutrients."""
    # Given an intake with no food
    intake = intake_factory(food=None)

    # When the intake without food is deleted
    intake.delete()

    # Then the day doesn't get its nutrients decreased
    assert intake.day.energy_kcal == 0


def test_no_food_str(intake_factory):
    """No food intake string representation doesn't contain food info."""
    # Given an intake with no food
    intake = intake_factory(food=None)

    # When the intake is converted to a string
    res = str(intake)

    # Then the string representation doesn't contain food info
    assert res == "Week 2 - Monday - Breakfast (No processed)"
