from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls, name="admin"),
    path("upload/", include("django_file_form.urls")),
    path("api/", include("core.urls")),
    path("vote/", include("vote.urls")),
]
