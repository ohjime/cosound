from django.urls import path
from . import views

app_name = "home"

urlpatterns = [
    path("", views.home_index, name="index"),
    path("load/", views.load, name="load"),
    path("swap/", views.swap, name="swap"),
    path("search/", views.search, name="search"),
    path("carousel/", views.carousel, name="carousel"),
    path(
        "collect/check_email/",
        views.collect_check_email,
        name="collect_check_email",
    ),
    path(
        "collect/check_code/",
        views.collect_check_code,
        name="collect_check_code",
    ),
    path(
        "collect/cancel/",
        views.collect_cancel,
        name="collect_cancel",
    ),
]
