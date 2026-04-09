from django.http import HttpResponse
from django.shortcuts import render

from core.models import Sound
from mix.models import Mix, MixLayer
from mix.utils import generate_sound_artwork, raise_alert
from vote.utils import get_random_avatar_url


def mix_index(request):
    return render(request, "mix/index.html")


def check_auth(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    if not request.user.is_authenticated:
        return render(request, "mix/index.html#login_required")

    sound_ids = list(Sound.objects.order_by("?")[:5].values_list("id", flat=True))
    request.session["mix_sound_ids"] = sound_ids

    sounds = list(Sound.objects.filter(id__in=sound_ids))
    for sound in sounds:
        sound.current_gain = 0
        sound.artwork_url = generate_sound_artwork(sound)

    return render(
        request,
        "mix/index.html#mix_form",
        {
            "sounds": sounds,
            "avatar_url": get_random_avatar_url(request.user.pk),
            "username": request.user.username,
        },
    )


def save_mix(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    if not request.user.is_authenticated:
        return raise_alert(request, "You must be logged in to save mixes.", "alert-error")

    layers = []
    for key, value in request.POST.items():
        if key.startswith("gain_"):
            sound_id = key.split("_")[1]
            try:
                gain = float(value)
                sound = Sound.objects.get(id=sound_id)
                layers.append((sound, gain))
            except (Sound.DoesNotExist, ValueError, TypeError):
                continue

    if not layers:
        return raise_alert(request, "No layers to save.", "alert-error")

    mix = Mix.objects.create(user=request.user)
    for sound, gain in layers:
        MixLayer.objects.create(mix=mix, sound=sound, user=request.user, gain=gain)

    return raise_alert(request, "Mix saved successfully!", "alert-success")
