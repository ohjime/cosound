import json


def parse_layers(raw):
    """Split a posted mix into its raw form and the (sound_id, gain) pairs.

    Layers whose id is not a Sound's are dropped rather than raised on. Two
    kinds never have one: a blank layer the `+` button made room for, and a
    track from the artist's own machine — both carry a browser-made string id.
    The save buttons already refuse a mix holding either, so this is the
    backstop for a request that arrives anyway, and it answers "no layers"
    instead of a 500.
    """
    try:
        layer_data = json.loads(raw or "[]")
    except (json.JSONDecodeError, ValueError):
        return None, None
    layers = []
    for layer in layer_data:
        try:
            sound_id = int(layer["sound_id"])
        except (KeyError, TypeError, ValueError):
            continue
        gain = max(0.0, min(1.0, float(layer.get("sound_gain", 1.0))))
        layers.append((sound_id, gain))
    return layer_data, layers


def generate_sound_artwork(sound):
    return "https://picsum.photos/seed/{}/400/400".format(sound.id)


# How many layers the mixer opens on, and how many of those start audible.
#
# Well under the eight-layer cap on purpose: the `+` on the layer indicator is
# what fills the rest in, so a listener arrives with room to build rather than a
# mix that is already finished.
OPENING_LAYERS = 3
OPENING_AUDIBLE_LAYERS = 2


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

    sound_ids = list(
        Sound.objects.order_by("?")[:OPENING_LAYERS].values_list("id", flat=True)
    )
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
    for sound in sounds[OPENING_AUDIBLE_LAYERS:]:
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
            "artist": sound.artist_name,
        }
        for sound in sounds
    ]
