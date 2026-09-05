"""Focused residual coverage for non-food GraphQL modules."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.exercises.models import DaySteps, Exercise
from apps.exercises.schema import ExerciseMutation, ExerciseQuery
from apps.goals.models import FatPercGoal
from apps.goals.schema import GoalMutation, GoalQuery
from apps.libs.graphql import (
    validated_decimal_field,
    validated_percentage_decimal,
)
from apps.measurements.models import Measurement
from apps.measurements.schema import MeasurementMutation, MeasurementQuery
from apps.plans.models import Day


def _context_with_request_user(is_authenticated: bool) -> SimpleNamespace:
    """Build a minimal Strawberry context object with request.user."""
    user = SimpleNamespace(is_authenticated=is_authenticated)
    return SimpleNamespace(
        context=SimpleNamespace(request=SimpleNamespace(user=user))
    )


def _context_with_user_object(
    is_authenticated: bool = True,
) -> SimpleNamespace:
    """Alias kept for readability in auth-oriented test cases."""
    return _context_with_request_user(is_authenticated=is_authenticated)


@pytest.mark.parametrize(
    "resolver_name",
    ["exercise", "day_steps", "measurement"],
)
def test_query_unauthenticated_returns_none(resolver_name: str) -> None:
    """Cover unauthenticated returns for query resolvers."""
    user_ctx = _context_with_request_user(is_authenticated=False)
    if resolver_name == "exercise":
        assert ExerciseQuery().exercise(user_ctx, id="1") is None
    elif resolver_name == "day_steps":
        assert ExerciseQuery().day_steps(user_ctx, id="1") is None
    else:
        assert MeasurementQuery().measurement(user_ctx, id="1") is None


def test_exercise_query_success_path_with_mocked_queryset(mocker) -> None:
    """Cover Exercise query success and serialization path."""
    exercise_ctx = _context_with_user_object()
    query = ExerciseQuery()

    model = SimpleNamespace()
    model_result = SimpleNamespace(id="7")

    mocker.patch(
        "apps.exercises.schema.Exercise.objects.get", return_value=model
    )
    from_model = mocker.patch(
        "apps.exercises.schema.ExerciseType.from_model",
        return_value=model_result,
    )

    assert query.exercise(exercise_ctx, id="1") is model_result
    from_model.assert_called_once_with(model)


def test_exercise_query_not_found_returns_none(mocker) -> None:
    """Cover Exercise.query not-found branch."""
    exercise_ctx = _context_with_user_object()
    mocker.patch(
        "apps.exercises.schema.Exercise.objects.get",
        side_effect=Exercise.DoesNotExist,
    )

    assert ExerciseQuery().exercise(exercise_ctx, id="1") is None


def test_day_steps_list_empty_for_unauth_and_success_when_authorized(
    mocker,
) -> None:
    """Cover unauthenticated and success list-return branches."""
    assert (
        ExerciseQuery().day_steps_list(_context_with_request_user(False)) == []
    )

    day_steps_ctx = _context_with_user_object()
    day_steps = [SimpleNamespace()]
    day_steps_filter = mocker.MagicMock()
    day_steps_filter.select_related.return_value.order_by.return_value = (
        day_steps
    )

    modelized = SimpleNamespace(id="11", steps=123)
    mocker.patch(
        "apps.exercises.schema.DaySteps.objects.filter",
        return_value=day_steps_filter,
    )
    from_model = mocker.patch(
        "apps.exercises.schema.DayStepsType.from_model",
        return_value=modelized,
    )

    got = ExerciseQuery().day_steps_list(day_steps_ctx)

    assert len(got) == 1
    assert got[0] is modelized
    day_steps_filter.select_related.assert_called_once_with("step_import")
    day_steps_filter.select_related.return_value.order_by.assert_called_once_with(
        "-day__day"
    )
    from_model.assert_has_calls([mocker.call(day_steps[0])])


def test_day_steps_query_success_and_not_found(mocker) -> None:
    """Cover DaySteps single-query success and not-found branch."""
    day_steps_ctx = _context_with_user_object()

    model = SimpleNamespace()
    mapped = SimpleNamespace(id="12", steps=321)
    queryset = mocker.MagicMock()
    queryset.get.return_value = model
    select_related = mocker.patch(
        "apps.exercises.schema.DaySteps.objects.select_related",
        return_value=queryset,
    )
    from_model = mocker.patch(
        "apps.exercises.schema.DayStepsType.from_model",
        return_value=mapped,
    )
    assert ExerciseQuery().day_steps(day_steps_ctx, id="1") is mapped
    select_related.assert_called_once_with("step_import")
    from_model.assert_called_once_with(model)

    queryset.get.side_effect = DaySteps.DoesNotExist
    assert ExerciseQuery().day_steps(day_steps_ctx, id="missing") is None


def test_exercise_mutations_auth_gate_forbidden() -> None:
    """Cover permission failures for all exercise mutations."""
    mutation = ExerciseMutation()
    ctx = _context_with_request_user(is_authenticated=False)

    with pytest.raises(PermissionError, match="Authentication required"):
        mutation.create_exercise(ctx, day_id=1, type="walk", kcals=10)
    with pytest.raises(PermissionError, match="Authentication required"):
        mutation.update_exercise(ctx, id="1", type="walk", kcals=10)
    with pytest.raises(PermissionError, match="Authentication required"):
        mutation.delete_exercise(ctx, id="1")
    with pytest.raises(PermissionError, match="Authentication required"):
        mutation.create_day_steps(ctx, day_id=1, steps=100)
    with pytest.raises(PermissionError, match="Authentication required"):
        mutation.update_day_steps(ctx, id="1", steps=100)
    with pytest.raises(PermissionError, match="Authentication required"):
        mutation.delete_day_steps(ctx, id="1")


def test_exercise_mutation_not_found_and_validation_errors(mocker) -> None:
    """Cover not-found branches and mutation error paths."""
    mutation = ExerciseMutation()
    ctx = _context_with_user_object()

    mocker.patch(
        "apps.plans.models.Day.objects.get", side_effect=Day.DoesNotExist
    )
    with pytest.raises(ValueError, match="Day not found"):
        mutation.create_exercise(ctx, day_id=999, type="walk", kcals=10)
    create_steps = mocker.patch(
        "apps.health_sync.services.create_manual_day_steps",
        side_effect=ValueError("Day not found"),
    )
    with pytest.raises(ValueError, match="Day not found"):
        mutation.create_day_steps(ctx, day_id=999, steps=100)
    create_steps.assert_called_once()

    mocker.patch(
        "apps.exercises.schema.Exercise.objects.get",
        side_effect=Exercise.DoesNotExist,
    )
    with pytest.raises(ValueError, match="Exercise not found"):
        mutation.update_exercise(ctx, id="1", type="walk", kcals=10)
    with pytest.raises(ValueError, match="Exercise not found"):
        mutation.delete_exercise(ctx, id="1")

    mocker.patch(
        "apps.health_sync.services.update_manual_day_steps",
        side_effect=ValueError("Day steps not found"),
    )
    mocker.patch(
        "apps.health_sync.services.delete_manual_day_steps",
        side_effect=ValueError("Day steps not found"),
    )
    with pytest.raises(ValueError, match="Day steps not found"):
        mutation.update_day_steps(ctx, id="1", steps=100)
    with pytest.raises(ValueError, match="Day steps not found"):
        mutation.delete_day_steps(ctx, id="1")


def test_update_day_steps_success_returns_serialized_value(mocker) -> None:
    """Cover successful DaySteps update path and save path."""
    mutation = ExerciseMutation()
    stored = mocker.MagicMock(steps=5)
    mapped = SimpleNamespace(id="3", steps=5)
    mocked_ctx = _context_with_user_object()

    update_steps = mocker.patch(
        "apps.health_sync.services.update_manual_day_steps",
        return_value=stored,
    )
    from_model = mocker.patch(
        "apps.exercises.schema.DayStepsType.from_model",
        return_value=mapped,
    )

    result = mutation.update_day_steps(mocked_ctx, id="3", steps=5)

    assert result is mapped
    update_steps.assert_called_once_with(mocked_ctx.context.request.user, 3, 5)
    from_model.assert_called_once_with(stored)


def test_goal_query_error_paths_and_mutation_auth_and_notfound(mocker) -> None:
    """Cover auth and not-found branches for Goal resolvers."""
    goal_query = GoalQuery()
    goal_mutation = GoalMutation()
    authenticated_ctx = _context_with_user_object()
    unauthenticated_ctx = _context_with_request_user(False)

    assert goal_query.fat_perc_goal(unauthenticated_ctx, id="1") is None

    mocker.patch(
        "apps.goals.schema.FatPercGoal.objects.get",
        side_effect=FatPercGoal.DoesNotExist,
    )
    assert goal_query.fat_perc_goal(authenticated_ctx, id="1") is None

    with pytest.raises(PermissionError, match="Authentication required"):
        goal_mutation.create_fat_perc_goal(
            unauthenticated_ctx, body_fat_perc=42
        )
    with pytest.raises(PermissionError, match="Authentication required"):
        goal_mutation.update_fat_perc_goal(
            unauthenticated_ctx, id="1", body_fat_perc=42
        )
    with pytest.raises(PermissionError, match="Authentication required"):
        goal_mutation.delete_fat_perc_goal(unauthenticated_ctx, id="1")

    mocker.patch(
        "apps.goals.schema.FatPercGoal.objects.get",
        side_effect=FatPercGoal.DoesNotExist,
    )
    with pytest.raises(ValueError, match="Goal not found"):
        goal_mutation.delete_fat_perc_goal(authenticated_ctx, id="1")


def test_measurement_query_and_mutation_auth_and_not_found(mocker) -> None:
    """Cover auth errors and not-found branch for measurement query."""
    query = MeasurementQuery()
    mutation = MeasurementMutation()
    authenticated_ctx = _context_with_user_object()
    unauthenticated_ctx = _context_with_request_user(False)

    assert query.measurement(unauthenticated_ctx, id="1") is None

    mocker.patch(
        "apps.measurements.schema.Measurement.objects.get",
        side_effect=Measurement.DoesNotExist,
    )
    assert query.measurement(authenticated_ctx, id="1") is None

    with pytest.raises(PermissionError, match="Authentication required"):
        mutation.update_measurement(
            unauthenticated_ctx,
            id="1",
            body_fat_perc=12.5,
            weight=70,
        )
    with pytest.raises(PermissionError, match="Authentication required"):
        mutation.delete_measurement(unauthenticated_ctx, id="1")


def test_graphql_decimal_helpers() -> None:
    """Cover previously uncovered graphql decimal helper branches."""
    with pytest.raises(
        ValueError, match="bodyFatPerc exceeds supported precision"
    ):
        validated_decimal_field(
            Decimal("1.23"),
            "bodyFatPerc",
            FatPercGoal._meta.get_field("body_fat_perc"),
        )

    assert validated_percentage_decimal(12.5, "bodyFatPerc") == Decimal("12.5")
