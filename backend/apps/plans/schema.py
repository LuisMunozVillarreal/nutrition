"""Plans, Days, and Intakes GraphQL schema module."""

# pylint: disable=too-few-public-methods

import datetime
from decimal import Decimal

import strawberry
from strawberry.types import Info

from apps.measurements.models import Measurement
from apps.plans.models import Day, Intake, WeekPlan


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
    tdee: float

    @strawberry.field
    def intakes(self) -> list[IntakeType]:
        """Get intakes for this day.

        Returns:
            list[IntakeType]: list of intakes.
        """
        # We need to access the django instance.
        # But `self` is a DayType wrapper.
        # We handle this by querying the intakes for this ID.
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
        return DayType(
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
            tdee=float(obj.tdee) if obj.tdee else 0.0,
        )


@strawberry.type
class WeekPlanType:
    """GraphQL WeekPlan Type."""

    id: strawberry.ID
    start_date: str
    protein_g_kg: float
    fat_perc: float
    deficit: int
    completed: bool
    twee: float
    energy_kcal_goal: float
    energy_kcal: float

    @strawberry.field
    def days(self) -> list[DayType]:
        """Get days for this plan.

        Returns:
            list[DayType]: list of days.
        """
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
        return WeekPlanType(
            id=strawberry.ID(str(obj.id)),
            start_date=obj.start_date.isoformat(),
            protein_g_kg=float(obj.protein_g_kg),
            fat_perc=float(obj.fat_perc),
            deficit=obj.deficit,
            completed=obj.completed,
            twee=float(obj.twee),
            energy_kcal_goal=float(obj.energy_kcal_goal),
            energy_kcal=float(obj.energy_kcal),
        )


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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return []

        return [
            WeekPlanType.from_model(p)
            for p in WeekPlan.objects.filter(user=user).order_by("-start_date")
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        try:
            obj = WeekPlan.objects.get(pk=id, user=user)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        try:
            obj = Day.objects.get(pk=id, plan__user=user)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            Measurement.objects.get(pk=measurement_id, user=user)
        except Measurement.DoesNotExist as e:
            raise ValueError("Measurement not found") from e

        obj = WeekPlan.objects.create(
            user=user,
            measurement_id=measurement_id,
            start_date=datetime.date.fromisoformat(start_date),
            protein_g_kg=Decimal(str(protein_g_kg)),
            fat_perc=Decimal(str(fat_perc)),
            deficit=deficit,
        )
        return WeekPlanType.from_model(obj)

    @strawberry.mutation
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = WeekPlan.objects.get(pk=id, user=user)
        except WeekPlan.DoesNotExist as e:
            raise ValueError("WeekPlan not found") from e

        obj.protein_g_kg = Decimal(str(protein_g_kg))
        obj.fat_perc = Decimal(str(fat_perc))
        obj.deficit = deficit
        obj.save()
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            day = Day.objects.get(pk=day_id, plan__user=user)
        except Day.DoesNotExist as e:
            raise ValueError("Day not found") from e

        # If food_id is not provided, we must set nutrients directly.
        # This mirrors the flexibility of Django admin for Intakes.
        kwargs = {
            "day": day,
            "meal": meal,
            "num_servings": Decimal(str(num_servings)),
        }

        if food_id:
            kwargs["food_id"] = int(food_id)
        else:
            kwargs["energy_kcal"] = Decimal(str(energy_kcal or 0))
            kwargs["protein_g"] = Decimal(str(protein_g or 0))
            kwargs["fat_g"] = Decimal(str(fat_g or 0))
            kwargs["carbs_g"] = Decimal(str(carbs_g or 0))

        obj = Intake.objects.create(**kwargs)
        return IntakeType.from_model(obj)

    @strawberry.mutation
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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Intake.objects.get(pk=id, day__plan__user=user)
        except Intake.DoesNotExist as e:
            raise ValueError("Intake not found") from e

        obj.meal = meal
        obj.num_servings = Decimal(str(num_servings))

        # Update nutrients directly ONLY if there's no food assigned or if
        # modifying custom intakes.
        if not obj.food_id:
            if energy_kcal is not None:
                obj.energy_kcal = Decimal(str(energy_kcal))
            if protein_g is not None:
                obj.protein_g = Decimal(str(protein_g))
            if fat_g is not None:
                obj.fat_g = Decimal(str(fat_g))
            if carbs_g is not None:
                obj.carbs_g = Decimal(str(carbs_g))

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
        request = getattr(info.context, "request", None)
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            raise PermissionError("Authentication required")

        try:
            obj = Intake.objects.get(pk=id, day__plan__user=user)
        except Intake.DoesNotExist as e:
            raise ValueError("Intake not found") from e

        obj.delete()
        return True
