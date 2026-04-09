from django.urls import path
from . import views

app_name = "mix"

urlpatterns = [
    path("", views.mix_index, name="index"),
    path("check_auth/", views.check_auth, name="check_auth"),
    path("save/", views.save_mix, name="save_mix"),
]
