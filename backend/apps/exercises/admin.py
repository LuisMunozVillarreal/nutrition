"""exercises app admin config module."""

# Admin hooks retain Django's callback signatures even when arguments are unused.
# pylint: disable=missing-param-doc,missing-return-doc,unused-argument

from typing import Any

from django.contrib import admin
from django.db import models, router, transaction
from django.http import HttpRequest

from apps.health_sync.services import (
    delete_manual_exercise,
    update_manual_exercise,
)
from apps.libs.admin import round_field
from apps.plans.locks import lock_plan_owner
from apps.plans.models import Day

from .models import DaySteps, Exercise


def _save_exercise(obj: Exercise) -> None:
    """Persist one admin form without a second model save after the service."""
    if obj._state.adding:  # pylint: disable=protected-access
        obj.save()
    else:
        original = Exercise.objects.select_related("day__plan__user").get(
            pk=obj.pk
        )
        update_manual_exercise(
            original.day.plan.user,
            obj.pk,
            exercise_type=obj.type,
            kcals=obj.kcals,
            time=obj.time,
            duration=obj.duration,
            distance=obj.distance,
            target_day=obj.day,
        )


class ExerciseInlineAdmin(admin.ModelAdmin):
    """Route exercise formsets through the same manual-write services."""

    def save_model(
        self, request: HttpRequest, obj: Any, form: Any, change: bool
    ) -> None:
        """Lock owners before the parent save and its exercise formsets."""
        using = router.db_for_write(self.model)
        owner_field = "plan__user_id" if self.model is Day else "user_id"
        owner_ids = {obj.plan.user_id if self.model is Day else obj.user_id}
        # Django's changeform transaction keeps these locks through save_related.
        with transaction.atomic(using=using):
            if change:
                owner_ids.update(
                    self.model.objects.using(using)
                    .filter(pk=obj.pk)
                    .values_list(owner_field, flat=True)
                )
            for owner_id in sorted(owner_ids):
                lock_plan_owner(using=using, user_id=owner_id)
            super().save_model(request, obj, form, change)

    def save_formset(
        self, request: HttpRequest, form: Any, formset: Any, change: bool
    ) -> None:
        """Retain normal inline handling for every unrelated model."""
        if formset.model is not Exercise:
            super().save_formset(request, form, formset, change)
            return
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            delete_manual_exercise(obj.day.plan.user, obj.pk)
        for obj in instances:
            _save_exercise(obj)
        formset.save_m2m()


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    """ExerciseAdmin class."""

    list_display = [
        "id",
        "day_time",
        "type",
        "kcals",
        "duration",
        round_field("distance"),
    ]

    def save_model(
        self, request: HttpRequest, obj: Exercise, form: Any, change: bool
    ) -> None:
        """Preserve manual edits against subsequent provider replays."""
        _save_exercise(obj)

    def delete_model(self, request: HttpRequest, obj: Exercise) -> None:
        """Detach provenance atomically with the exercise deletion."""
        delete_manual_exercise(obj.day.plan.user, obj.pk)

    def delete_queryset(
        self, request: HttpRequest, queryset: models.QuerySet[Exercise]
    ) -> None:
        """Lock every owner before deleting a batch through the service."""
        using = queryset.db
        with transaction.atomic(using=using):
            owner_ids = sorted(
                set(queryset.values_list("day__plan__user_id", flat=True))
            )
            for owner_id in owner_ids:
                lock_plan_owner(using=using, user_id=owner_id)
            for exercise in queryset.select_related(
                "day__plan__user"
            ).order_by("pk"):
                self.delete_model(request, exercise)


@admin.register(DaySteps)
class DayStepsAdmin(admin.ModelAdmin):
    """DayStepsAdmin class."""

    list_display = [
        "id",
        "day",
        "steps",
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Prevent writes that bypass canonical aggregate locks."""
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: DaySteps | None = None
    ) -> bool:
        """Keep imported provenance consistent by making rows view-only."""
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: DaySteps | None = None
    ) -> bool:
        """Require deletes to pass through the owner-scoped service."""
        return False


class ExerciseInlineBase:
    """Exercise inline class."""

    # pylint: disable=too-few-public-methods

    model = Exercise
    extra = 0
    show_change_link = True

    fields = [
        "type",
        "kcals",
        "duration",
        "distance",
    ]


class DayStepsInlineBase:
    """DaySteps inline class."""

    # pylint: disable=too-few-public-methods

    model = DaySteps
    extra = 0
    show_change_link = False
    can_delete = False

    fields = [
        "steps",
        "kcals",
    ]

    readonly_fields = ["steps", "kcals"]

    def has_add_permission(
        self, request: HttpRequest, obj: Any | None = None
    ) -> bool:
        """Prevent inline creation outside the canonical service."""
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: Any | None = None
    ) -> bool:
        """Prevent inline edits from retaining stale provenance."""
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: Any | None = None
    ) -> bool:
        """Prevent inline deletes with inverted lock ordering."""
        return False
