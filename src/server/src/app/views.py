from django.http import HttpResponse
from django.shortcuts import render

from core.models import Listener
from explore.renderer import get_explore_context
from library.models import SoundMix
from library.utils import get_empty_layer
from studio.utils import get_artist


def example_card_page(request):
    return render(request, "example/example_card.html")


def example_card_initial(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(
        request,
        "example/example_card.html#initial",
    )


def example_card_swap_figure(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(
        request,
        "example/example_card.html#new-figure",
    )


def example_card_swap_body(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(
        request,
        "example/example_card.html#new-body",
    )


def example_card_swap_header(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(
        request,
        "example/example_card.html#new-header",
    )


def example_card_swap_multiple(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(
        request,
        "example/example_card.html#new-multiple",
    )


def home_page(request):
    return render(request, "app/home.html")


def home_initial(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(
        request,
        "app/home.html#initial",
        get_explore_context(request.user),
    )


def home_tab_library(request):
    """Render the LIBRARY tab over a fresh empty layer."""
    if not request.htmx:
        return HttpResponse("Request Denied.")

    liked_sound_count = 0
    saved_mix_count = 0
    if request.user.is_authenticated:
        listener = Listener.objects.filter(user=request.user).first()
        if listener is not None:
            liked_sound_count = listener.collection.count()
        saved_mix_count = SoundMix.objects.filter(creator=request.user).count()

    return render(
        request,
        "app/home.html#tab_library",
        {
            "sounds": [get_empty_layer()],
            "liked_sound_count": liked_sound_count,
            "saved_mix_count": saved_mix_count,
        },
    )


def home_tab_studio(request):
    """Render the STUDIO tab: the library's card over one blank layer, where
    the blank layer can be filled from the library or created as a new sound.

    Artists only — the tab is not drawn for anyone else, and this refuses them
    too rather than trusting that.
    """
    if not request.htmx:
        return HttpResponse("Request Denied.")
    artist = get_artist(request.user)
    if artist is None:
        return HttpResponse("Request Denied.", status=403)

    return render(
        request,
        "app/home.html#tab_studio",
        {"sounds": [get_empty_layer()], "artist": artist},
    )


def home_tab_about(request):
    """The ABOUT tab's body: the static cosound write-up (no context needed)."""
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(request, "app/home.html#tab_about")
