"""nutrition URL Configuration."""

from django.contrib import admin
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from graphene_django.views import GraphQLView

urlpatterns = [
    path("admin/", admin.site.urls),
    # pylint: disable=fixme
    # TODO: Once authentication is added, remove the csrf_exempt
    path("graphql", csrf_exempt(GraphQLView.as_view(graphiql=True))),
]
