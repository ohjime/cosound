from django.urls import path
from . import views

app_name = "mix"

urlpatterns = [
    path("", views.mix_index, name="index"),
    path("load/", views.load, name="load"),
]
