import random
from datetime import datetime, timezone

from django.tasks import task

from core.models import Cosound, Sound, SoundLayer, Player
from voter.models import Vote


@task
def predictor_v1(
    player_id: int,
    *args,
    **kwargs,
) -> int:
    """
    Predictor V1: A vote-aware cosound prediction algorithm.

    Rules:
    - If no cosound exists: randomly assign 3 soundscape layers (gain 0.5-1.0)
    - If cosound exists:
        - Replace one random layer with a new random soundscape (gain 0.5-1.0)
        - If votes exist since last cosound.created_at: add 1 instrumental (gain 0.1-0.4)
        - If no recent votes and instrumental exists: remove the instrumental
    """
    player = Player.objects.get(pk=player_id)

    # Fetch all sounds from the player's library
    soundscapes = list(player.library.filter(type="Soundscape"))
    instrumentals = list(player.library.filter(type="Instrumental"))

    # Get the current cosound from the player
    current_cosound = player.playing

    # Check if there's an existing cosound with at least 3 layers
    has_sufficient_layers = (
        current_cosound and current_cosound.layers and len(current_cosound.layers) >= 3
    )

    if not has_sufficient_layers:
        # No cosound or less than 3 layers: randomly assign 3 soundscape layers with gain 0.5-1.0
        layers: list[SoundLayer] = [
            sound.asLayer(with_gain=random.uniform(0.5, 1.0))
            for sound in random.sample(
                soundscapes,
                min(3, len(soundscapes)),
            )
        ]
        cosound = Cosound(layers=layers) if layers else None
    else:
        # There is a cosound - work with existing layers
        current_layers = list(current_cosound.layers)

        # Separate soundscape and instrumental layers
        soundscape_layers = [l for l in current_layers if l.sound_type == "Soundscape"]
        instrumental_layers = [
            l for l in current_layers if l.sound_type == "Instrumental"
        ]

        # Randomly select one soundscape layer and replace it with a random new one
        if soundscape_layers and soundscapes:
            # Pick a random index to replace
            replace_idx = random.randint(0, len(soundscape_layers) - 1)

            # Get IDs of current soundscape layers to avoid duplicates if possible
            current_soundscape_ids = {l.sound_id for l in soundscape_layers}
            available_soundscapes = [
                s for s in soundscapes if str(s.pk) not in current_soundscape_ids
            ]

            # If no unique soundscapes available, use all soundscapes
            if not available_soundscapes:
                available_soundscapes = soundscapes

            # Pick a random replacement
            new_sound = random.choice(available_soundscapes)
            soundscape_layers[replace_idx] = new_sound.asLayer(
                with_gain=random.uniform(0.5, 1.0)
            )

        # Check for votes since the last cosound was created
        votes_since_cosound = Vote.objects.filter(
            player=player,
            created_at__gte=current_cosound.created_at,
        )
        has_recent_votes = votes_since_cosound.exists()

        if has_recent_votes:
            # Add 1 instrumental layer if we have instrumentals available
            if instrumentals:
                # Get IDs of current instrumental layers to avoid duplicates if possible
                current_instrumental_ids = {l.sound_id for l in instrumental_layers}
                available_instrumentals = [
                    i
                    for i in instrumentals
                    if str(i.pk) not in current_instrumental_ids
                ]

                if not available_instrumentals:
                    available_instrumentals = instrumentals

                new_instrumental = random.choice(available_instrumentals)
                instrumental_layers.append(
                    new_instrumental.asLayer(with_gain=random.uniform(0.3, 0.5))
                )
        else:
            # No recent votes: remove instrumental layers if any exist
            instrumental_layers = []

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
