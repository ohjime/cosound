import random
from datetime import datetime, timezone

from django.tasks import task

from core.models import Cosound, Sound, SoundLayer, Player
from voter.models import Vote


@task
def predictor_v1(
    player_id: int,
) -> int:
    """
    Predictor V1: vote-aware cosound prediction algorithm.

    Every 180s per player:
    - Remove any existing instrumental layers.
    - If the player has at least 3 soundscape layers:
        - Replace one random soundscape with a new one the player does
          not already contain (if available), gain in [0.5, 1.0].
    - Else (fewer than 3 soundscape layers):
        - Add new, non-duplicate soundscape layers until there are 3
          (or we run out), each with gain in [0.5, 1.0].
    - If any new votes exist since the last player update:
        - Add exactly one instrumental layer with gain in [0.3, 0.45].
    """
    player = Player.objects.get(pk=player_id)

    # Fetch all sounds from the player's library
    soundscapes = list(player.library.filter(type="Soundscape"))
    instrumentals = list(player.library.filter(type="Instrumental"))

    # Current cosound and layers
    current_cosound: Cosound | None = player.playing
    current_layers = list(current_cosound.layers) if current_cosound else []

    # Separate soundscape and instrumental layers
    soundscape_layers: list[SoundLayer] = [
        l for l in current_layers if l.sound_type == "Soundscape"
    ]
    instrumental_layers: list[SoundLayer] = []  # always start with none

    # ----------
    # Soundscapes
    # ----------
    current_soundscape_ids = {l.sound_id for l in soundscape_layers}

    if len(soundscape_layers) >= 3:
        # Swap one existing soundscape with a new one (if available)
        if soundscapes:
            replace_idx = random.randint(0, len(soundscape_layers) - 1)

            available_soundscapes = [
                s for s in soundscapes if str(s.pk) not in current_soundscape_ids
            ]
            if not available_soundscapes:
                # Fallback: allow reuse if library smaller than needed
                available_soundscapes = soundscapes

            new_sound = random.choice(available_soundscapes)
            soundscape_layers[replace_idx] = new_sound.asLayer(
                with_gain=random.uniform(0.5, 1.0)
            )
    else:
        # Fewer than 3 soundscapes: add until we reach 3
        available_soundscapes = [
            s for s in soundscapes if str(s.pk) not in current_soundscape_ids
        ]

        while len(soundscape_layers) < 3 and (available_soundscapes or soundscapes):
            # Prefer non-duplicates when possible
            pool = available_soundscapes if available_soundscapes else soundscapes
            new_sound = random.choice(pool)
            soundscape_layers.append(
                new_sound.asLayer(with_gain=random.uniform(0.5, 1.0))
            )
            if new_sound in available_soundscapes:
                available_soundscapes.remove(new_sound)

    # -----------------
    # Votes / Instrument
    # -----------------
    # Determine last update time from the existing cosound, if any
    if current_cosound and getattr(current_cosound, "created_at", None):
        last_update_at = current_cosound.created_at
    else:
        # If for some reason we don't have a timestamp, treat as "ever"
        last_update_at = datetime.fromtimestamp(0, tz=timezone.utc)

    has_recent_votes = Vote.objects.filter(
        player=player,
        created_at__gte=last_update_at,
    ).exists()

    if has_recent_votes and instrumentals:
        # Add exactly one instrumental layer
        new_instrumental = random.choice(instrumentals)
        instrumental_layers.append(
            new_instrumental.asLayer(with_gain=random.uniform(0.3, 0.45))
        )

    # Combine layers back together
    new_layers = soundscape_layers + instrumental_layers
    cosound = Cosound(layers=new_layers) if new_layers else None

    if cosound:
        player.playing = cosound
        player.save()
        print(f"Now Playing at \033[1m{player.name}\033[22m:")
        print(player.summary())
    else:
        print(f"No New Prediction for \033[1m{player.name}\033[22m")

    return 1 if cosound else 0
