"""nutrition URL Configuration."""

import django_sql_dashboard
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("dashboard/", include(django_sql_dashboard.urls)),
    path("_nested_admin/", include("nested_admin.urls")),
]
