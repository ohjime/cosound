import json


def parse_layers(raw):
    try:
        layer_data = json.loads(raw or "[]")
    except (json.JSONDecodeError, ValueError):
        return None, None
    layers = [
        (int(l["sound_id"]), max(0.0, min(1.0, float(l.get("sound_gain", 1.0)))))
        for l in layer_data
    ]
    return layer_data, layers


def generate_sound_artwork(sound):
    return "https://picsum.photos/seed/{}/400/400".format(sound.id)


def get_random_sounds(user=None):
    import random
    from core.models import Listener, Sound

    saved_ids = set()
    if user and user.is_authenticated:
        try:
            saved_ids = set(
                Listener.objects.get(user=user).collection.values_list("id", flat=True)
            )
        except Listener.DoesNotExist:
            pass

    sound_ids = list(Sound.objects.order_by("?")[:8].values_list("id", flat=True))
    sounds = [
        {
            **sound.asLayer(with_gain=round(random.uniform(0.1, 0.9), 2)),
            "artwork_url": sound.art.url if sound.art else "",
            "mute": False,
            "saved": sound.pk in saved_ids,
            "flavor": sound.flavor or "",
            "tags": " / ".join(sound.tags.names()) or "Unknown",
        }
        for sound in Sound.objects.filter(id__in=sound_ids).prefetch_related("tags")
    ]
    for sound in sounds[2:]:
        sound["mute"] = True
    return sounds


def serialize_sounds(sounds):
    return [
        {
            **sound.asLayer(with_gain=0.5),
            "gain": 50,
            "mute": False,
            "saved": True,
            "flavor": sound.flavor or "",
            "tags": " / ".join(sound.tags.names()) or "Unknown",
            "artwork_url": generate_sound_artwork(sound),
            "id": sound.id,
            "title": sound.title,
            "artist": sound.artist,
        }
        for sound in sounds
    ]
