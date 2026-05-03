import math
from datetime import timedelta

from django.conf import settings
from django.db.models import Max
from django.utils import timezone

from core.models import Listener, Player, Sound

VOTE_THROTTLE_WINDOW = timedelta(seconds=getattr(settings, "VOTE_THROTTLE_SECONDS", 60))


def build_vote_context(request):
    token = request.GET.get("player")
    section = request.GET.get("section") or None
    choice = request.GET.get("choice")

    player = None
    if token:
        player = (
            Player.objects.select_related("manager").filter(token=token).first()
        )

    layers = serialize_player_for_carousel(player) if player else []

    throttle_seconds_left = 0
    if request.user.is_authenticated:
        listener = Listener.objects.filter(user=request.user).first()
        if listener:
            throttle_seconds_left = get_throttle_seconds_left(listener)

    return {
        "player": player,
        "choice": choice,
        "section": section,
        "layers": layers,
        "throttle_seconds_left": throttle_seconds_left,
    }


def serialize_player_for_carousel(player):
    """Carousel layer list. Index 0 = player info; 1..N = sound layers."""
    items = [
        {
            "kind": "player",
            "sound_id": None,
            "sound_file": "",
            "sound_gain": None,
            "sound_title": player.name,
            "sound_artist": player.manager.name if player.manager else "",
            "artwork_url": player.photo.url if player.photo else "",
            "bio": player.bio or "",
            "gain": None,
            "flavor": "",
            "tags": "",
            "location": player.location or "Unknown",
        }
    ]

    layer_objs = list(player.playing.layers)
    sound_ids = [l.sound_id for l in layer_objs]
    sounds = {
        s.pk: s
        for s in Sound.objects.filter(pk__in=sound_ids).prefetch_related("tags")
    }
    for l in layer_objs:
        sound = sounds.get(l.sound_id)
        if sound is None:
            continue
        items.append(
            {
                "kind": "layer",
                **sound.asLayer(with_gain=l.sound_gain),
                "artwork_url": sound.art.url if sound.art else "",
                "gain": int(round(l.sound_gain * 100)),
                "flavor": sound.flavor or "",
                "tags": " / ".join(sound.tags.names()) or "Unknown",
                "bio": "",
                "location": "",
            }
        )
    return items


def get_throttle_seconds_left(listener, window: timedelta = VOTE_THROTTLE_WINDOW):
    """Seconds remaining before this listener can vote again (0 if not throttled)."""
    last_vote_at = _last_vote_at(listener)
    if last_vote_at is None:
        return 0
    now = timezone.now()
    if now - last_vote_at >= window:
        return 0
    return math.ceil((last_vote_at + window - now).total_seconds())


def _last_vote_at(listener):
    # Imported lazily to avoid a circular import (vote.models -> vote.utils).
    from vote.models import Vote

    return Vote.objects.filter(voter=listener).aggregate(last=Max("created_at"))["last"]
