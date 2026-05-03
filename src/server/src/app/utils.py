def serialize_mix(sm):
    layers = []
    for sl in sm.cosound.soundlayer_set.all():
        gain = float(sl.gain)
        layers.append(
            {
                **sl.sound.asLayer(with_gain=gain),
                "artwork_url": sl.sound.art.url if sl.sound.art else "",
                "mute": False,
                "isolated": False,
                "saved": True,
                "flavor": sl.sound.flavor or "",
                "tags": " / ".join(sl.sound.tags.names()) or "Unknown",
                "gain": int(round(gain * 100)),
            }
        )
    return {
        "id": sm.id,
        "cosound_id": sm.cosound_id,
        "title": sm.title,
        "created_at": sm.created_at.isoformat(),
        "layers": layers,
    }


def serialize_user_mixes(user):
    from mixer.models import SoundMix

    if not user or not user.is_authenticated:
        return []
    mixes = (
        SoundMix.objects.filter(creator=user)
        .select_related("cosound")
        .prefetch_related("cosound__soundlayer_set__sound__tags")
        .order_by("-created_at")
    )
    return [serialize_mix(sm) for sm in mixes]
