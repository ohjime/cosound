from django.http import HttpResponse
from django.shortcuts import render

from core.models import Sound
from mix.utils import generate_sound_artwork


def mix_index(request):
    return render(request, "mix/index.html")


def load(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    sound_ids = list(Sound.objects.order_by("?")[:10].values_list("id", flat=True))
    sounds = list(Sound.objects.filter(id__in=sound_ids))
    for sound in sounds:
        sound.current_gain = 0
        sound.artwork_url = generate_sound_artwork(sound)

    return render(
        request,
        "mix/index.html#mix_player",
        {"sounds": sounds},
    )
