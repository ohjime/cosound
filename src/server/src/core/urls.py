from django.urls import path

from core.api import api
from core.views import (
    card_example_index,
    card_example_initial,
    card_example_swap_figure,
    card_example_swap_body,
    card_example_swap_header,
    card_example_swap_multiple,
)

app_name = "core"

urlpatterns = [
    path(
        "examples/card",
        card_example_index,
        name="card_example",
    ),
]

htmx_urlpatterns = [
    path(
        "htmx/examples/card/initial",
        card_example_initial,
        name="card_example_initial",
    ),
    path(
        "htmx/examples/card/swap-figure",
        card_example_swap_figure,
        name="card_example_swap_figure",
    ),
    path(
        "htmx/examples/card/swap-body",
        card_example_swap_body,
        name="card_example_swap_body",
    ),
    path(
        "htmx/examples/card/swap-header",
        card_example_swap_header,
        name="card_example_swap_header",
    ),
    path(
        "htmx/examples/card/swap-multiple",
        card_example_swap_multiple,
        name="card_example_swap_multiple",
    ),
]

urlpatterns += htmx_urlpatterns
