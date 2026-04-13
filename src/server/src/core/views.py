from django.http import HttpResponse
from django.shortcuts import render

from core.models import Sound
from home.utils import generate_sound_artwork


def card_example_index(request):
    return render(request, "core/card-example.html")


def card_example_initial(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(
        request,
        "core/card-example.html#initial",
    )


def card_example_swap_figure(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(
        request,
        "core/card-example.html#new-figure",
    )


def card_example_swap_body(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(
        request,
        "core/card-example.html#new-body",
    )


def card_example_swap_header(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(
        request,
        "core/card-example.html#new-header",
    )
