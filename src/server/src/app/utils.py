def _visible_to_creator(sound, creator_id):
    """Whether the mix's owner may still hear this layer.

    A sound pulled from publication is gone from every saved mix but those of
    the artist who uploaded it. Checked in Python rather than with a query so
    the prefetch the saved list makes still covers it.
    """
    if sound.published:
        return True
    return sound.artist is not None and sound.artist.user_id == creator_id


def serialize_mix(sm):
    layers = []
    for sl in sm.cosound.soundlayer_set.all():
        if not _visible_to_creator(sl.sound, sm.creator_id):
            continue
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
