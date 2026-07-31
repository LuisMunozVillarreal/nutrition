"""Recipe models module."""

# pylint: disable=cyclic-import

from decimal import Decimal
from typing import Any, Collection, Iterable, cast

from django.db import models, router, transaction

from .food import Food
from .nutrients import NUTRIENT_LIST, Nutrients
from .units import UNIT_CHOICES, UNIT_CONTAINER, UNIT_SERVING


class _RecipeIngredientOwnerChanged(Exception):
    """Signal that provisional recipe locks missed the authoritative owner."""


class RecipeIngredientQuerySet(models.QuerySet):
    """QuerySet that globally prelocks recipe hierarchies before collection."""

    def delete(self) -> tuple[int, dict[str, int]]:
        """Delete ingredients under one Recipe-to-RecipeIngredient lock pass.

        Returns:
            tuple[int, dict[str, int]]: Total and per-model deletion counts.
        """
        using = self.db
        recipe_ids = tuple(
            self.order_by().values_list("recipe_id", flat=True).distinct()
        )
        from apps.foods.recipe_locks import (
            activate_recipe_aggregate_locks,
            lock_recipe_aggregate_rows,
        )

        with transaction.atomic(using=using):
            locks = lock_recipe_aggregate_rows(recipe_ids, using)
            with activate_recipe_aggregate_locks(locks):
                return super().delete()


class RecipeIngredientManager(
    models.Manager.from_queryset(RecipeIngredientQuerySet)  # type: ignore[misc]
):
    """Manager exposing deletion-safe RecipeIngredient querysets."""


class Recipe(Food):
    """Recipe models class."""

    _PROTECTED_WRITE_FIELDS = frozenset(
        NUTRIENT_LIST
        + [
            "nutrients_from_ingredients",
            "nutritional_info_size",
            "nutritional_info_unit",
            "size",
            "size_unit",
            "num_servings",
        ]
    )
    _loaded_protected_write_values: dict[str, Any]

    description = models.TextField(
        blank=True,
    )

    nutrients_from_ingredients = models.BooleanField(
        default=False,
        verbose_name="Calculate nutrients from ingredients",
    )

    @classmethod
    def from_db(
        cls,
        db: str | None,
        field_names: Collection[str],
        values: Collection[Any],
    ) -> "Recipe":
        """Remember loaded protected values for stale-safe full model saves.

        Args:
            db: Database alias from which the row was loaded.
            field_names: Model fields included in the query.
            values: Values returned for those fields.

        Returns:
            The hydrated recipe with its protected-field baseline captured.
        """
        instance = cast("Recipe", super().from_db(db, field_names, values))
        # Django's polymorphic from_db return type is narrower than its stubs.
        # pylint: disable-next=protected-access,no-member
        instance._capture_protected_write_values()
        return instance

    def refresh_from_db(
        self,
        using: str | None = None,
        fields: Iterable[str] | None = None,
        from_queryset: models.QuerySet[Any] | None = None,
    ) -> None:
        """Reload values and synchronize refreshed protected baselines.

        Args:
            using: Database alias from which to reload.
            fields: Optional concrete fields to reload.
            from_queryset: Optional queryset used for the reload.
        """
        normalized_fields = None if fields is None else tuple(fields)
        refreshed_fields = self._refreshed_protected_write_fields(
            normalized_fields, from_queryset
        )
        super().refresh_from_db(
            using=using,
            fields=normalized_fields,
            from_queryset=from_queryset,
        )
        self._capture_protected_write_values(refreshed_fields)

    def _refreshed_protected_write_fields(
        self,
        fields: Collection[str] | None,
        from_queryset: models.QuerySet[Any] | None,
    ) -> set[str]:
        """Return protected fields the refresh queryset will actually load."""
        deferred_fields = self.get_deferred_fields()
        refreshed_fields = set(self._PROTECTED_WRITE_FIELDS)
        if fields is not None:
            refreshed_fields.intersection_update(fields)
        else:
            refreshed_fields.difference_update(deferred_fields)
        if from_queryset is None:
            return refreshed_fields

        reload_queryset = from_queryset
        if fields is not None:
            reload_queryset = reload_queryset.only(*fields)
        elif deferred_fields:
            reload_queryset = reload_queryset.only(
                *{
                    field.attname
                    for field in self._meta.concrete_fields
                    if field.attname not in deferred_fields
                }
            )
        selected_fields, defer = reload_queryset.query.deferred_loading
        if not selected_fields:
            return refreshed_fields
        selected_field_names = {
            field.split("__", maxsplit=1)[0] for field in selected_fields
        }
        if defer:
            return refreshed_fields - selected_field_names
        return refreshed_fields & selected_field_names

    def _capture_protected_write_values(
        self, fields: Collection[str] | None = None
    ) -> None:
        """Record protected values represented by this caller instance."""
        loaded = (
            {}
            if fields is None
            else dict(getattr(self, "_loaded_protected_write_values", {}))
        )
        captured_fields = self._PROTECTED_WRITE_FIELDS
        if fields is not None:
            captured_fields = captured_fields & set(fields)
        loaded.update(
            {
                field: getattr(self, field)
                for field in captured_fields
                if field not in self.get_deferred_fields()
            }
        )
        self._loaded_protected_write_values = loaded

    def _reconcile_protected_write_values(
        self,
        authoritative: "Recipe",
        update_fields: set[str] | None,
        protected_update_fields: set[str],
    ) -> None:
        """Copy protected fields not intentionally owned by this write."""
        if update_fields is not None:
            caller_owned = update_fields & self._PROTECTED_WRITE_FIELDS
        else:
            loaded = getattr(self, "_loaded_protected_write_values", {})
            caller_owned = {
                field
                for field, original in loaded.items()
                if getattr(self, field) != original
            }
            caller_owned.update(protected_update_fields)
        for field in self._PROTECTED_WRITE_FIELDS - caller_owned:
            setattr(self, field, getattr(authoritative, field))

    @property
    def num_ingredients(self) -> int:
        """Get number of ingredients.

        Returns:
            str: number of ingredients.
        """
        return self.ingredients.count()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Serialize recipe writes with ingredients and preserve derived totals.

        Full saves own protected fields only when they changed since this model
        instance was loaded. Partial saves own protected fields explicitly named
        in ``update_fields``. Callers constructing an existing instance manually
        may name intentional protected fields in ``_protected_update_fields``.

        Args:
            args (Any): positional model save arguments.
            kwargs (Any): keyword model save arguments.
        """
        skip_aggregate_lock = kwargs.pop("_skip_aggregate_lock", False)
        protected_update_fields: set[str] = set(
            kwargs.pop("_protected_update_fields", ())
        )
        if self.pk is None or skip_aggregate_lock:
            super().save(*args, **kwargs)
            self._capture_protected_write_values()
            return

        using = kwargs.get("using") or router.db_for_write(
            type(self), instance=self
        )
        from apps.foods.recipe_locks import lock_recipe_ingredients
        from apps.foods.signals.handlers.recipe_nutrients import (
            apply_recipe_ingredient_totals,
        )

        with transaction.atomic(using=using):
            recipes, ingredients = lock_recipe_ingredients([self.pk], using)
            if self.pk not in recipes:
                raise type(self).DoesNotExist(
                    "Recipe was deleted before this write acquired its locks"
                )
            update_fields = kwargs.get("update_fields")
            normalized_update_fields = (
                None if update_fields is None else set(update_fields)
            )
            self._reconcile_protected_write_values(
                recipes[self.pk],
                normalized_update_fields,
                protected_update_fields,
            )
            apply_recipe_ingredient_totals(self, ingredients)
            if (
                self.nutrients_from_ingredients
                and normalized_update_fields is not None
            ):
                kwargs["update_fields"] = normalized_update_fields | set(
                    NUTRIENT_LIST + ["size"]
                )
            super().save(*args, **kwargs)
            self._capture_protected_write_values()

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return f"{self.name} ({self.num_servings}s)"


class RecipeIngredient(Nutrients):
    """RecipeIngredient models class."""

    objects = RecipeIngredientManager()

    recipe = models.ForeignKey(
        "foods.Recipe",
        on_delete=models.CASCADE,
        related_name="ingredients",
    )

    food = models.ForeignKey(
        "foods.Serving",
        on_delete=models.CASCADE,
        related_name="recipes",
    )

    num_servings = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=1,
    )

    size_snapshot = models.DecimalField(
        max_digits=20,
        decimal_places=10,
        null=True,
        editable=False,
        help_text="Total ingredient size captured from its serving when saved.",
    )

    size_snapshot_unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        null=True,
        editable=False,
    )

    def __str__(self) -> str:
        """Get string representation of the object.

        Returns:
            str: string representation of the object.
        """
        return (
            f"{self.recipe.name} - {str(self.food)}"
            f" {self.food.serving_size * self.num_servings} "
            f"({self.food.serving_unit})"
        )

    @property
    def size(self) -> Decimal:
        """Get the immutable total size of this ingredient.

        Returns:
            Decimal: captured or lazily resolved total size.
        """
        if self.size_snapshot is not None:
            return self.size_snapshot
        return self.food.size * self.num_servings

    @property
    def effective_size_snapshot_unit(self) -> str:
        """Return the snapshot unit, lazily resolving expansion-era rows.

        Returns:
            str: concrete unit associated with the ingredient size.
        """
        if self.size_snapshot_unit is not None:
            return self.size_snapshot_unit
        if self.food.serving_unit in (UNIT_CONTAINER, UNIT_SERVING):
            return self.food.food.size_unit
        return self.food.serving_unit

    def _prepare_snapshots(
        self,
        previous: "RecipeIngredient | None",
        update_fields: set[str] | None,
    ) -> set[str] | None:
        """Prepare immutable amount, unit, and nutrient snapshot fields."""
        from apps.foods.signals.handlers.recipe_nutrients import (
            validate_derived_decimal,
        )

        serving_changed = previous is None or (
            previous.food_id != self.food_id
            or previous.num_servings != self.num_servings
        )
        snapshot_fields: set[str] = set()
        current_size = self.food.size * self.num_servings
        current_unit = (
            self.food.food.size_unit
            if self.food.serving_unit in (UNIT_CONTAINER, UNIT_SERVING)
            else self.food.serving_unit
        )
        if serving_changed or self.size_snapshot is None:
            self.size_snapshot = validate_derived_decimal(
                current_size,
                type(self),
                "size_snapshot",
                "Recipe ingredient",
            )
            snapshot_fields.add("size_snapshot")
        if serving_changed or self.size_snapshot_unit is None:
            self.size_snapshot_unit = current_unit
            snapshot_fields.add("size_snapshot_unit")
        if serving_changed:
            for nutrient in NUTRIENT_LIST:
                value = getattr(self.food, nutrient) or 0
                setattr(
                    self,
                    nutrient,
                    validate_derived_decimal(
                        value * self.num_servings,
                        type(self),
                        nutrient,
                        "Recipe ingredient",
                    ),
                )
            snapshot_fields.update(NUTRIENT_LIST)
        return (
            None if update_fields is None else update_fields | snapshot_fields
        )

    def _save_with_provisional_owners(
        self, db_alias: str, *args: Any, **kwargs: Any
    ) -> tuple[dict[int, Recipe], Recipe | None]:
        """Perform one owner-lock attempt and reject a stale lock set."""
        aggregate_observer = cast(
            Recipe | None, self._state.fields_cache.get("recipe")
        )
        was_adding = self._state.adding
        previous_recipe_id = None
        if self.pk is not None:
            previous_recipe_id = (
                type(self)
                .objects.using(db_alias)
                .filter(pk=self.pk)
                .values_list("recipe_id", flat=True)
                .first()
            )
        recipe_ids = {self.recipe_id}
        if previous_recipe_id is not None:
            recipe_ids.add(previous_recipe_id)

        from apps.foods.recipe_locks import lock_recipe_ingredients
        from apps.foods.signals.handlers.recipe_nutrients import (
            recompute_recipe_nutrients,
            validate_recipe_ingredient_size,
        )

        recipes, ingredients = lock_recipe_ingredients(recipe_ids, db_alias)
        previous = next(
            (
                ingredient
                for ingredient in ingredients
                if ingredient.pk == self.pk
            ),
            None,
        )
        if self.pk is not None and previous is None:
            try:
                current = (
                    type(self)
                    .objects.select_for_update(of=("self",))
                    .using(db_alias)
                    .get(pk=self.pk)
                )
            except type(self).DoesNotExist:
                if not was_adding:
                    raise
            else:
                if current.recipe_id not in recipe_ids:
                    raise _RecipeIngredientOwnerChanged
                previous = current
        target_recipe = recipes[self.recipe_id]
        self.recipe = target_recipe
        update_fields = kwargs.get("update_fields")
        prepared_fields = self._prepare_snapshots(
            previous,
            None if update_fields is None else set(update_fields),
        )
        if prepared_fields is not None:
            kwargs["update_fields"] = prepared_fields
        validate_recipe_ingredient_size(self, target_recipe)
        super().save(*args, **kwargs)
        for recipe_id in sorted(recipe_ids):
            recompute_recipe_nutrients(recipes[recipe_id], db_alias)
        return recipes, aggregate_observer

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Lock, mutate, and authoritatively rebuild recipe aggregates atomically.

        A movable row's owner sampled before locks is provisional. If the locked
        child reveals a different owner, the attempt rolls back completely and
        restarts in a fresh transaction with a bounded retry count.

        Args:
            args (Any): positional model save arguments.
            kwargs (Any): keyword model save arguments.

        Raises:
            RuntimeError: If an outer transaction must be retried after a
                concurrent owner change, or the bounded retry is exhausted.
        """
        using = kwargs.get("using") or router.db_for_write(
            type(self), instance=self
        )
        from apps.foods.signals.handlers.recipe_nutrients import (
            synchronize_recipe_aggregates,
        )

        entered_in_atomic = transaction.get_connection(using).in_atomic_block
        for attempt in range(3):
            try:
                with transaction.atomic(using=using):
                    recipes, aggregate_observer = (
                        self._save_with_provisional_owners(
                            using, *args, **kwargs
                        )
                    )
                break
            except _RecipeIngredientOwnerChanged as error:
                if entered_in_atomic or attempt == 2:
                    raise RuntimeError(
                        "Recipe ingredient owner changed while acquiring locks; "
                        "retry the outer transaction"
                    ) from error
        else:  # pragma: no cover - the bounded loop always breaks or raises
            raise RuntimeError("recipe ingredient lock retry exhausted")
        target_recipe = recipes[self.recipe_id]
        if aggregate_observer is not None and synchronize_recipe_aggregates(
            target_recipe, aggregate_observer
        ):
            self.recipe = aggregate_observer
