from django.urls import path
from . import views

app_name = "home"

urlpatterns = [
    path("", views.home_index, name="index"),
    path("load/", views.load, name="load"),
    path("swap/", views.swap, name="swap"),
    path("search/", views.search, name="search"),
    path("carousel/", views.carousel, name="carousel"),
]
