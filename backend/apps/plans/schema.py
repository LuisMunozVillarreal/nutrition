"""Plans, Days, and Intakes GraphQL schema module."""

# pylint: disable=too-few-public-methods

import datetime
from decimal import Decimal
from typing import cast

import strawberry
from django.conf import settings
from django.db import models, router, transaction
from django.db.models import Prefetch
from strawberry.types import Info

from apps.libs.graphql import (
    get_request_user,
    validated_non_negative_decimal,
    validated_percentage_decimal,
    validated_positive_decimal,
)
from apps.measurements.models import Measurement
from apps.plans.locks import lock_plan_aggregate_rows
from apps.plans.models import Day, Intake, WeekPlan

# WeekPlanType fields that traverse the days relation (and therefore need the
# batched day prefetch to avoid per-plan query growth).
_DAY_DEPENDENT_FIELDS = frozenset(
    {
        "days",
        "twee",
        "energyKcalGoal",
        "energyKcal",
    }
)


def _requested_field_names(info: Info) -> set[str]:
    """Return the GraphQL field names selected on the current field's type."""
    names: set[str] = set()
    for field in info.selected_fields:
        for selection in field.selections:
            name = getattr(selection, "name", None)
            if name:
                names.add(name)
    return names


def _day_queryset() -> models.QuerySet:
    """Build the Day queryset with all TDEE dependencies preloaded.

    Selects the plan measurement and reverse one-to-one steps, prefetches
    intakes, and annotates the exercise calories aggregate so ``tdee`` and
    ``twee`` never issue per-day SQL.
    """
    return (
        Day.objects.select_related("plan__measurement", "steps")
        .prefetch_related(
            Prefetch(
                "intakes",
                queryset=Intake.objects.order_by("meal_order", "created_at"),
            )
        )
        .annotate(eat_total=models.Sum("exercises__kcals"))
        .order_by("day")
    )


def _day_tdee(day: Day) -> Decimal:
    """Compute a day's TDEE from prefetched or annotated data.

    Mirrors ``Day.tdee`` but consumes the batched plan measurement, steps,
    intakes, and the annotated exercise total instead of issuing queries.

    Args:
        day (Day): the day model instance.

    Returns:
        Decimal: the total daily energy expenditure.
    """
    if not day.tracked:
        return (day.plan.measurement.bmr * day.plan.EXERCISE_RATE).normalize()

    if hasattr(day, "steps"):
        neat = day.steps.kcals
    else:
        neat = Decimal("0")
    tef = day.energy_kcal * Decimal("0.1")
    if hasattr(day, "eat_total"):
        eat_total = Decimal(day.eat_total or 0)
    else:
        eat_total = Decimal(day.eat or 0)
    return day.plan.measurement.bmr + neat + tef + eat_total


def _validated_week_plan_parameters(
    measurement: Measurement,
    protein_g_kg: float,
    fat_perc: float,
    deficit: int,
    tdee_values: list[Decimal] | None = None,
    daily_deficits: list[Decimal] | None = None,
) -> tuple[Decimal, Decimal, int]:
    """Validate plan inputs and every resulting daily nutrition goal."""
    validated_protein_g_kg = validated_positive_decimal(
        protein_g_kg,
        "proteinGKg",
        WeekPlan._meta.get_field("protein_g_kg"),
    )
    validated_fat_perc = validated_percentage_decimal(
        fat_perc,
        "fatPerc",
        WeekPlan._meta.get_field("fat_perc"),
    )
    validated_deficit = validated_non_negative_decimal(deficit, "deficit")
    protein_g_goal = validated_protein_g_kg * measurement.weight
    daily_tdee_values = tdee_values or [
        measurement.bmr for _ in range(WeekPlan.PLAN_LENGTH_DAYS)
    ]
    daily_deficit_values = daily_deficits or [
        validated_deficit * Decimal(deficit_perc) / 100
        for deficit_perc in WeekPlan.DEFICIT_DISTRIBUTION
    ]

    if len(daily_tdee_values) != len(daily_deficit_values):
        raise ValueError("Every day must have a TDEE and deficit")

    for tdee, daily_deficit in zip(daily_tdee_values, daily_deficit_values):
        energy_kcal_goal = tdee - daily_deficit
        if not energy_kcal_goal.is_finite() or energy_kcal_goal <= 0:
            raise ValueError("energyKcalGoal must be greater than 0")
        fat_g_goal = (
            energy_kcal_goal
            * validated_fat_perc
            / 100
            / settings.FAT_KCAL_GRAM
        )
        carbs_g_goal = (
            energy_kcal_goal
            - fat_g_goal * settings.FAT_KCAL_GRAM
            - protein_g_goal * settings.PROTEIN_KCAL_GRAM
        ) / settings.CARB_KCAL_GRAM
        for field_name, goal in (
            ("proteinGGoal", protein_g_goal),
            ("fatGGoal", fat_g_goal),
            ("carbsGGoal", carbs_g_goal),
        ):
            if not goal.is_finite() or goal < 0:
                raise ValueError(
                    f"{field_name} must be greater than or equal to 0"
                )

    return validated_protein_g_kg, validated_fat_perc, int(validated_deficit)


@strawberry.type
class IntakeType:
    """GraphQL Intake Type."""

    id: strawberry.ID
    day_id: int
    food_id: strawberry.ID | None
    num_servings: float
    meal: str
    meal_order: int
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float

    @staticmethod
    def from_model(obj: Intake) -> "IntakeType":
        """Create IntakeType from model instance.

        Args:
            obj (Intake): model instance.

        Returns:
            IntakeType: GraphQL type.
        """
        return IntakeType(
            id=strawberry.ID(str(obj.id)),
            day_id=obj.day_id,
            food_id=strawberry.ID(str(obj.food_id)) if obj.food_id else None,
            num_servings=float(obj.num_servings),
            meal=obj.meal,
            meal_order=obj.meal_order,
            energy_kcal=float(obj.energy_kcal),
            protein_g=float(obj.protein_g),
            fat_g=float(obj.fat_g),
            carbs_g=float(obj.carbs_g),
        )


@strawberry.type
class DayType:
    """GraphQL Day Type."""

    id: strawberry.ID
    plan_id: int
    day: str
    day_num: int
    deficit: int
    tracked: bool
    completed: bool
    energy_kcal_goal: float
    protein_g_goal: float
    fat_g_goal: float
    carbs_g_goal: float
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    model: strawberry.Private[Day | None] = None

    @strawberry.field
    def intakes(self) -> list[IntakeType]:
        """Get intakes for this day.

        Returns:
            list[IntakeType]: list of intakes.
        """
        model = self.model
        if model is not None:
            return [IntakeType.from_model(i) for i in model.intakes.all()]
        return [
            IntakeType.from_model(i)
            for i in Intake.objects.filter(day_id=self.id).order_by(
                "meal_order", "created_at"
            )
        ]

    # Note: exercises and steps queries are handled in their own modules,
    # but could be added here later if needed.

    @staticmethod
    def from_model(obj: Day) -> "DayType":
        """Create DayType from model instance.

        Args:
            obj (Day): model instance.

        Returns:
            DayType: GraphQL type.
        """
        wrapped = DayType(
            id=strawberry.ID(str(obj.id)),
            plan_id=obj.plan_id,
            day=obj.day.isoformat(),
            day_num=obj.day_num,
            deficit=obj.deficit,
            tracked=obj.tracked,
            completed=obj.completed,
            energy_kcal_goal=(
                float(obj.energy_kcal_goal) if obj.energy_kcal_goal else 0.0
            ),
            protein_g_goal=(
                float(obj.protein_g_goal) if obj.protein_g_goal else 0.0
            ),
            fat_g_goal=float(obj.fat_g_goal) if obj.fat_g_goal else 0.0,
            carbs_g_goal=float(obj.carbs_g_goal) if obj.carbs_g_goal else 0.0,
            energy_kcal=float(obj.energy_kcal),
            protein_g=float(obj.protein_g),
            fat_g=float(obj.fat_g),
            carbs_g=float(obj.carbs_g),
        )
        wrapped.model = obj
        return wrapped

    @strawberry.field
    def tdee(self) -> float:
        """Resolve total daily energy expenditure when requested.

        Returns:
            float: total daily energy expenditure.
        """
        if self.model is None:
            return 0.0
        return float(_day_tdee(self.model))


@strawberry.type
class WeekPlanType:
    """GraphQL WeekPlan Type."""

    id: strawberry.ID
    start_date: str
    protein_g_kg: float
    fat_perc: float
    deficit: int
    completed: bool
    model: strawberry.Private[WeekPlan | None] = None

    @strawberry.field
    def days(self) -> list[DayType]:
        """Get days for this plan.

        Returns:
            list[DayType]: list of days.
        """
        model = self.model
        if model is not None:
            # The conditional week_plans/week_plan prefetch builds this cache
            # with _day_queryset(), so TDEE dependencies are already loaded.
            return [DayType.from_model(d) for d in model.days.all()]
        return [
            DayType.from_model(d)
            for d in Day.objects.filter(plan_id=int(str(self.id))).order_by(
                "day"
            )
        ]

    @staticmethod
    def from_model(obj: WeekPlan) -> "WeekPlanType":
        """Create WeekPlanType from model instance.

        Args:
            obj (WeekPlan): model instance.

        Returns:
            WeekPlanType: GraphQL type.
        """
        wrapped = WeekPlanType(
            id=strawberry.ID(str(obj.id)),
            start_date=obj.start_date.isoformat(),
            protein_g_kg=float(obj.protein_g_kg),
            fat_perc=float(obj.fat_perc),
            deficit=obj.deficit,
            completed=obj.completed,
        )
        wrapped.model = obj
        return wrapped

    @strawberry.field
    def twee(self) -> float:
        """Resolve TWEE when requested.

        Returns:
            float: total weekly energy expenditure estimate.
        """
        if self.model is None:
            return 0.0
        total = Decimal("0")
        for day in self.model.days.all():
            total += _day_tdee(day)
        return float(total)

    @strawberry.field
    def energy_kcal_goal(self) -> float:
        """Resolve energy goal when requested.

        Returns:
            float: weekly energy target.
        """
        if self.model is None:
            return 0.0
        return float(self.model.energy_kcal_goal)

    @strawberry.field
    def energy_kcal(self) -> float:
        """Resolve energy intake when requested.

        Returns:
            float: weekly accumulated energy intake.
        """
        if self.model is None:
            return 0.0
        return float(self.model.energy_kcal)


@strawberry.type
class PlanQuery:
    """Plan queries."""

    @strawberry.field
    def week_plans(self, info: Info) -> list[WeekPlanType]:
        """Get all week plans for the current user.

        Args:
            info (Info): GraphQL execution info.

        Returns:
            list[WeekPlanType]: list of week plans.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return []

        queryset = WeekPlan.objects.filter(user=user)
        if _requested_field_names(info) & _DAY_DEPENDENT_FIELDS:
            queryset = queryset.prefetch_related(
                Prefetch("days", queryset=_day_queryset())
            )
        return [
            WeekPlanType.from_model(p)
            for p in queryset.order_by("-start_date")
        ]

    @strawberry.field
    def week_plan(self, info: Info, id: strawberry.ID) -> WeekPlanType | None:
        """Get a single week plan.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): week plan ID.

        Returns:
            WeekPlanType | None: the plan or None.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return None

        try:
            queryset = WeekPlan.objects.filter(pk=id, user=user)
            if _requested_field_names(info) & _DAY_DEPENDENT_FIELDS:
                queryset = queryset.prefetch_related(
                    Prefetch("days", queryset=_day_queryset())
                )
            obj = queryset.get()
        except WeekPlan.DoesNotExist:
            return None
        return WeekPlanType.from_model(obj)

    @strawberry.field
    def day(self, info: Info, id: strawberry.ID) -> DayType | None:
        """Get a single day.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): day ID.

        Returns:
            DayType | None: the day or None.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return None

        try:
            obj = Day.objects.prefetch_related(
                Prefetch(
                    "intakes",
                    queryset=Intake.objects.order_by(
                        "meal_order", "created_at"
                    ),
                )
            ).get(pk=id, plan__user=user)
        except Day.DoesNotExist:
            return None
        return DayType.from_model(obj)

    @strawberry.field
    def intake(self, info: Info, id: strawberry.ID) -> IntakeType | None:
        """Get a single intake.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): intake ID.

        Returns:
            IntakeType | None: the intake or None.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            return None

        try:
            obj = Intake.objects.get(pk=id, day__plan__user=user)
        except Intake.DoesNotExist:
            return None
        return IntakeType.from_model(obj)


@strawberry.type
class PlanMutation:
    """Plan mutations."""

    @strawberry.mutation
    @transaction.atomic
    def create_week_plan(
        self,
        info: Info,
        start_date: str,
        protein_g_kg: float,
        fat_perc: float,
        deficit: int,
        measurement_id: int,
    ) -> WeekPlanType:
        """Create a new week plan.

        Args:
            info (Info): GraphQL execution info.
            start_date (str): the start date in ISO format.
            protein_g_kg (float): target protein in g/kg.
            fat_perc (float): target fat percentage.
            deficit (int): daily energy deficit.
            measurement_id (int): the starting measurement ID.

        Returns:
            WeekPlanType: the created week plan.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if measurement not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            measurement = Measurement.objects.get(pk=measurement_id, user=user)
        except Measurement.DoesNotExist as e:
            raise ValueError("Measurement not found") from e

        validated_protein, validated_fat, validated_deficit = (
            _validated_week_plan_parameters(
                measurement, protein_g_kg, fat_perc, deficit
            )
        )

        obj = WeekPlan.objects.create(
            user=user,
            measurement_id=measurement_id,
            start_date=datetime.date.fromisoformat(start_date),
            protein_g_kg=validated_protein,
            fat_perc=validated_fat,
            deficit=validated_deficit,
        )
        return WeekPlanType.from_model(obj)

    @strawberry.mutation
    @transaction.atomic
    def update_week_plan(
        self,
        info: Info,
        id: strawberry.ID,
        protein_g_kg: float,
        fat_perc: float,
        deficit: int,
    ) -> WeekPlanType:
        """Update an existing week plan.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): week plan ID.
            protein_g_kg (float): target protein in g/kg.
            fat_perc (float): target fat percentage.
            deficit (int): daily energy deficit.

        Returns:
            WeekPlanType: the updated week plan.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if week plan not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = WeekPlan.objects.get(pk=id, user=user)
        except WeekPlan.DoesNotExist as e:
            raise ValueError("WeekPlan not found") from e

        day_ids = tuple(obj.days.order_by("pk").values_list("pk", flat=True))
        aggregate_locks = lock_plan_aggregate_rows(
            using=router.db_for_write(WeekPlan, instance=obj),
            plan_ids=(obj.pk,),
            day_ids=day_ids,
        )
        obj = aggregate_locks.plans_by_pk[obj.pk]
        days = sorted(aggregate_locks.days, key=lambda day: day.day_num)
        try:
            validated_protein, validated_fat, validated_deficit = (
                _validated_week_plan_parameters(
                    obj.measurement,
                    protein_g_kg,
                    fat_perc,
                    deficit,
                    [day.tdee for day in days],
                )
            )
            obj.protein_g_kg = validated_protein
            obj.fat_perc = validated_fat
            obj.deficit = validated_deficit
            obj.save()
            for day, deficit_perc in zip(days, obj.DEFICIT_DISTRIBUTION):
                day.deficit = obj.deficit * deficit_perc / 100
                day.save()
        finally:
            aggregate_locks.clear_markers()
        return WeekPlanType.from_model(obj)

    @strawberry.mutation
    def delete_week_plan(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a week plan.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): week plan ID.

        Returns:
            bool: True if deleted.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if week plan not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = WeekPlan.objects.get(pk=id, user=user)
        except WeekPlan.DoesNotExist as e:
            raise ValueError("WeekPlan not found") from e

        obj.delete()
        return True

    @strawberry.mutation
    def update_day(
        self,
        info: Info,
        id: strawberry.ID,
        tracked: bool,
    ) -> DayType:
        """Update an existing day.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): day ID.
            tracked (bool): whether the day was tracked.

        Returns:
            DayType: the updated day.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if day not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Day.objects.get(pk=id, plan__user=user)
        except Day.DoesNotExist as e:
            raise ValueError("Day not found") from e

        obj.tracked = tracked
        obj.save()
        return DayType.from_model(obj)

    @strawberry.mutation
    @transaction.atomic
    def create_intake(
        self,
        info: Info,
        day_id: int,
        meal: str,
        num_servings: float,
        food_id: strawberry.ID | None = None,
        energy_kcal: float | None = None,
        protein_g: float | None = None,
        fat_g: float | None = None,
        carbs_g: float | None = None,
    ) -> IntakeType:
        """Create a new intake.

        Args:
            info (Info): GraphQL execution info.
            day_id (int): day ID.
            meal (str): meal name.
            num_servings (float): number of servings.
            food_id (strawberry.ID | None): food product ID.
            energy_kcal (float | None): energy in kcal.
            protein_g (float | None): protein in g.
            fat_g (float | None): fat in g.
            carbs_g (float | None): carbs in g.

        Returns:
            IntakeType: the created intake.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if day not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")
        validated_num_servings = validated_positive_decimal(
            num_servings,
            "numServings",
            Intake._meta.get_field("num_servings"),
        )
        validated_meal = Intake.validate_meal(meal)

        try:
            day = Day.objects.get(pk=day_id, plan__user=user)
        except Day.DoesNotExist as e:
            raise ValueError("Day not found") from e

        # If food_id is not provided, we must set nutrients directly.
        # This mirrors the flexibility of Django admin for Intakes.
        kwargs = {
            "day": day,
            "meal": validated_meal,
            "num_servings": validated_num_servings,
        }

        if food_id:
            kwargs["food_id"] = int(food_id)
        else:
            kwargs["energy_kcal"] = validated_non_negative_decimal(
                energy_kcal if energy_kcal is not None else 0,
                "energyKcal",
                Intake._meta.get_field("energy_kcal"),
            )
            kwargs["protein_g"] = validated_non_negative_decimal(
                protein_g if protein_g is not None else 0,
                "proteinG",
                Intake._meta.get_field("protein_g"),
            )
            kwargs["fat_g"] = validated_non_negative_decimal(
                fat_g if fat_g is not None else 0,
                "fatG",
                Intake._meta.get_field("fat_g"),
            )
            kwargs["carbs_g"] = validated_non_negative_decimal(
                carbs_g if carbs_g is not None else 0,
                "carbsG",
                Intake._meta.get_field("carbs_g"),
            )

        obj = Intake.objects.create(**kwargs)
        return IntakeType.from_model(obj)

    @strawberry.mutation
    @transaction.atomic
    def update_intake(
        self,
        info: Info,
        id: strawberry.ID,
        meal: str,
        num_servings: float,
        energy_kcal: float | None = None,
        protein_g: float | None = None,
        fat_g: float | None = None,
        carbs_g: float | None = None,
    ) -> IntakeType:
        """Update an existing intake.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): intake ID.
            meal (str): meal name.
            num_servings (float): number of servings.
            energy_kcal (float | None): energy in kcal.
            protein_g (float | None): protein in g.
            fat_g (float | None): fat in g.
            carbs_g (float | None): carbs in g.

        Returns:
            IntakeType: the updated intake.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if intake not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Intake.objects.get(pk=id, day__plan__user=user)
        except Intake.DoesNotExist as e:
            raise ValueError("Intake not found") from e

        validated_num_servings = validated_positive_decimal(
            num_servings,
            "numServings",
            Intake._meta.get_field("num_servings"),
        )
        validated_nutrients = {}
        if not obj.food_id:
            for model_field, field_name, value in (
                ("energy_kcal", "energyKcal", energy_kcal),
                ("protein_g", "proteinG", protein_g),
                ("fat_g", "fatG", fat_g),
                ("carbs_g", "carbsG", carbs_g),
            ):
                if value is not None:
                    validated_nutrients[model_field] = (
                        validated_non_negative_decimal(
                            value,
                            field_name,
                            cast(
                                models.DecimalField,
                                Intake._meta.get_field(model_field),
                            ),
                        )
                    )

        obj.meal = Intake.validate_meal(meal)
        obj.num_servings = validated_num_servings

        # Food-backed nutrients are derived and cannot be directly modified.
        for model_field, validated_value in validated_nutrients.items():
            setattr(obj, model_field, validated_value)

        obj.save()
        return IntakeType.from_model(obj)

    @strawberry.mutation
    def delete_intake(self, info: Info, id: strawberry.ID) -> bool:
        """Delete an intake.

        Args:
            info (Info): GraphQL execution info.
            id (strawberry.ID): intake ID.

        Returns:
            bool: True if deleted.

        Raises:
            PermissionError: if user is not authenticated.
            ValueError: if intake not found.
        """
        user = get_request_user(info.context)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Intake.objects.get(pk=id, day__plan__user=user)
        except Intake.DoesNotExist as e:
            raise ValueError("Intake not found") from e

        obj.delete()
        return True
