from django.contrib import admin
from django.urls import path, include

from app.api import api_urls


urlpatterns = [
    path("", include("app.urls")),
    path("card-demo/", include("card_demo.urls")),
    path("api/", api_urls),
    path("login/", include("login.urls")),
    path("library/", include("library.urls")),
    path("vote/", include("vote.urls")),
    path("profile/", include("profile.urls")),
    path("explore/", include("explore.urls")),
    path("admin/", admin.site.urls, name="admin"),
    path("upload/", include("config.file_upload_urls")),
]
