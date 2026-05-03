from django.contrib import admin
from django.urls import path, include

from app.api import api


urlpatterns = [
    path("", include("app.urls")),
    path("api/", api.urls),
    path("login/", include("login.urls")),
    path("mixer/", include("mixer.urls")),
    path("vote/", include("vote.urls")),
    path("admin/", admin.site.urls, name="admin"),
    path("upload/", include("django_file_form.urls")),
]
