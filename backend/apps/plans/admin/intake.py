"""Intake admin config module."""

import copy
import datetime
from typing import Any, Dict

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from apps.foods.signals.handlers.cupboard import (
    CupboardItemConsumptionTooBigError,
)
from apps.libs.admin import round_field

from ..models import Day, Intake, IntakePicture


class IntakePictureInline(admin.TabularInline):
    """Intake picture inline class."""

    model = IntakePicture
    extra = 0
    show_change_link = True


@admin.register(Intake)
class IntakeAdmin(admin.ModelAdmin):
    """Intake admin class."""

    # pylint: disable=duplicate-code

    inlines = [
        IntakePictureInline,
    ]

    ordering = [
        "-day__plan",
        "-day__day",
        "-meal_order",
    ]

    autocomplete_fields = [
        "food",
    ]

    list_filter = [
        "processed",
    ]

    list_display = [
        "id",
        "day",
        "food",
        round_field("num_servings"),
        "meal",
        "processed",
        round_field("energy"),
        round_field("protein_g"),
        round_field("fat_g"),
        round_field("carbs_g"),
        "created_at",
    ]

    fields = [
        "day",
        "food",
        "num_servings",
        "meal",
        "notes",
        "processed",
        "energy",
        "protein_g",
        "fat_g",
        "carbs_g",
        "created_at",
    ]

    readonly_fields = [
        "processed",
        "energy",
        "protein_g",
        "fat_g",
        "carbs_g",
        "created_at",
    ]

    def get_changeform_initial_data(self, request: HttpRequest) -> Dict:
        """Get initial data for the change form.

        Args:
            request (HttpRequest): request object.

        Returns:
            dict: initial data.
        """
        res: Dict[str, Any] = {}

        # Day
        day = Day.objects.filter(day=datetime.date.today()).first()
        if day:
            res["day"] = day.id

        # Meal
        time = datetime.datetime.now().time()
        if datetime.time(8) < time < datetime.time(12):
            res["meal"] = Intake.MEAL_BREAKFAST
        elif datetime.time(12) <= time < datetime.time(15):
            res["meal"] = Intake.MEAL_LUNCH
        elif datetime.time(15) <= time < datetime.time(20):
            res["meal"] = Intake.MEAL_SNACK
        else:
            res["meal"] = Intake.MEAL_DINNER

        return res

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: Dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Change view.

        Overriden to manage CupboardItemConsumptionTooBigError exceptions.

        Args:
            request (HttpRequest): request object.
            object_id (str | None): object id.
            form_url (str): form url.
            extra_context (Dict[str, Any]): extra context.

        Returns:
            HttpResponse: if the request is valid, or
            HttpResponseRedirect: redirect response.
        """
        try:
            return super().changeform_view(
                request, object_id, form_url, extra_context
            )
        except CupboardItemConsumptionTooBigError:
            self.message_user(
                request,
                "Intake can't be bigger than the cupboard item's quantity.",
                level=messages.ERROR,
            )
            return HttpResponseRedirect(request.path)


class IntakeInlineBase:
    """Intake inline class."""

    # pylint: disable=too-few-public-methods

    model = Intake
    extra = 0
    show_change_link = True

    autocomplete_fields = [
        "food",
    ]

    ordering = [
        "-day__plan",
        "-day__day",
        "meal_order",
    ]
    fields = copy.deepcopy(IntakeAdmin.fields)
    readonly_fields = copy.deepcopy(IntakeAdmin.readonly_fields)
