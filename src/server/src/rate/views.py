from django.http import HttpResponse
from django.shortcuts import render

from core.models import Sound
from rate.models import SoundRating
from rate.utils import generate_sound_artwork, raise_alert
from vote.utils import get_random_avatar_url


def rate_index(request):
    return render(request, "rate/index.html")


def check_auth(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    if not request.user.is_authenticated:
        return render(request, "rate/index.html#login_required")

    sound_ids = list(Sound.objects.order_by("?")[:5].values_list("id", flat=True))
    request.session["rate_sound_ids"] = sound_ids

    sounds = list(Sound.objects.filter(id__in=sound_ids))
    ratings_map = {
        r.sound_id: r.rating
        for r in SoundRating.objects.filter(user=request.user, sound__in=sounds)
    }
    for sound in sounds:
        sound.current_rating = ratings_map.get(sound.id, 0)
        sound.artwork_url = generate_sound_artwork(sound)

    return render(
        request,
        "rate/index.html#rate_form",
        {
            "sounds": sounds,
            "avatar_url": get_random_avatar_url(request.user.pk),
            "username": request.user.username,
        },
    )


def rate_sound(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    if not request.user.is_authenticated:
        return raise_alert(request, "You must be logged in to rate sounds.")

    sound_id = request.POST.get("sound_id")
    raw_rating = request.POST.get("rating")

    try:
        sound = Sound.objects.get(id=sound_id)
        rating = int(raw_rating)
        if not (1 <= rating <= 5):
            raise ValueError
    except (Sound.DoesNotExist, ValueError, TypeError):
        return raise_alert(request, "Invalid rating.")

    SoundRating.objects.update_or_create(
        user=request.user,
        sound=sound,
        defaults={"rating": rating},
    )

    return render(
        request,
        "rate/index.html#stars",
        {
            "sound_id": sound_id,
            "current_rating": rating,
        },
    )


def rate_sounds(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    if not request.user.is_authenticated:
        return raise_alert(request, "You must be logged in to rate sounds.", "error")

    for key, value in request.POST.items():
        if key.startswith("rating_"):
            sound_id = key.split("_")[1]
            try:
                rating = int(value)
                if 1 <= rating <= 5:
                    sound = Sound.objects.get(id=sound_id)
                    SoundRating.objects.update_or_create(
                        user=request.user,
                        sound=sound,
                        defaults={"rating": rating},
                    )
            except (Sound.DoesNotExist, ValueError, TypeError):
                continue

    return raise_alert(request, "Ratings saved successfully!", "success")
