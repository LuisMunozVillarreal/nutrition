"""Intake tests."""


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
