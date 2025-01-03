"""nutrition URL Configuration."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("_nested_admin/", include("nested_admin.urls")),
]
