from django.urls import path

from core.api import api

urlpatterns = [
    path("core/", api.urls),
]
