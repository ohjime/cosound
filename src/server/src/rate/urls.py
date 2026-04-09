from django.urls import path
from . import views

app_name = "rate"

urlpatterns = [
    path("", views.rate_index, name="index"),
    path("check_auth/", views.check_auth, name="check_auth"),
    path("rate/", views.rate_sound, name="rate_sound"),
    path("rate_all/", views.rate_sounds, name="rate_sounds"),
]
