"""nutrition URL Configuration."""

import django_sql_dashboard
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import RedirectView
from strawberry.django.views import AsyncGraphQLView

from config.schema import schema

urlpatterns = [
    path("_nested_admin/", include("nested_admin.urls")),
    path("admin/", admin.site.urls),
    path("dashboard/", include(django_sql_dashboard.urls)),
    path(
        "favicon.ico",
        RedirectView.as_view(url=settings.STATIC_URL + "favicon.ico"),
    ),
    path("graphql/", csrf_exempt(AsyncGraphQLView.as_view(schema=schema))),
]
