from django.contrib import admin
from django.urls import path, include
from core.api import api as core_api


urlpatterns = [
    path("", include("home.urls")),
    path("vote/", include("vote.urls")),
    path("rate/", include("rate.urls")),
    path("core/", include("core.urls")),
    path("api/core/", core_api.urls),
    path("admin/", admin.site.urls, name="admin"),
    path("upload/", include("django_file_form.urls")),
]
