from django.urls import path

from mixer.views import (
    mixer_index,
    mixer_save,
    mixer_save_confirm,
    mixer_keep_sound,
    mixer_swap,
    mixer_search,
    mixer_carousel,
)

app_name = "mixer"

urlpatterns = [
    path("", mixer_index, name="index"),
    path("save/", mixer_save, name="save"),
    path("save/confirm/", mixer_save_confirm, name="save_confirm"),
    path("keep-sound/", mixer_keep_sound, name="keep_sound"),
    path("swap/", mixer_swap, name="swap"),
    path("search/", mixer_search, name="search"),
    path("carousel/", mixer_carousel, name="carousel"),
]
