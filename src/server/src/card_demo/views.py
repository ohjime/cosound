from django.shortcuts import render

from core.models import Sound


def card_demo(request):
    sounds = (
        Sound.objects.select_related("artist")
        .prefetch_related("tags")
        .order_by("pk")[:8]
    )
    slides = [
        {
            "sound_id": sound.pk,
            "sound_title": sound.title,
            "sound_artist": sound.artist_name,
            "artwork_url": sound.art.url if sound.art else "",
            "flavor": sound.flavor or "This sound is part of the Co-Sound collection.",
            "tags": " / ".join(sound.tags.names()) or "Sound",
            "gain": 70,
        }
        for sound in sounds
    ]
    return render(request, "card_demo/index.html", {"sounds": slides})
