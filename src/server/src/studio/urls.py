from django.urls import path

from studio.views import (
    studio_carousel,
    studio_create_sound,
    studio_index,
    studio_initial,
    studio_library,
    studio_library_search,
    studio_tag_search,
)

app_name = "studio"

urlpatterns = [
    path("", studio_index, name="index"),
]

htmx_urlpatterns = [
    path("htmx/initial", studio_initial, name="initial"),
    path("htmx/library", studio_library, name="library"),
    path("htmx/library/search", studio_library_search, name="library_search"),
    path("htmx/carousel", studio_carousel, name="carousel"),
    path("htmx/tags", studio_tag_search, name="tag_search"),
    path("htmx/sounds/create", studio_create_sound, name="create_sound"),
]

urlpatterns += htmx_urlpatterns
