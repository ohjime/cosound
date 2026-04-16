import random

from django.http import HttpResponse
from django.shortcuts import render

from core.models import Sound
from home.utils import generate_sound_artwork


def home_index(request):
    return render(request, "home/index.html")


def load(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    sound_ids = list(Sound.objects.order_by("?")[:8].values_list("id", flat=True))
    sounds = [
        {
            **sound.asLayer(with_gain=round(random.uniform(0.1, 0.9), 2)).model_dump(),
            "artwork_url": generate_sound_artwork(sound),
            "mute": False,
            "flavor": sound.flavor or "",
            "tags": " / ".join(sound.tags.names()) or "Unknown",
        }
        for sound in Sound.objects.filter(id__in=sound_ids).prefetch_related("tags")
    ]

    return render(
        request,
        "home/index.html#home_player",
        {"sounds": sounds},
    )


def swap(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(request, "home/index.html#swap_view")


def carousel(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(request, "home/index.html#carousel_view")
