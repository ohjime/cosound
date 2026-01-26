import random
from django.tasks import task
from core.models import Cosound, SoundLayer, Player


@task
def random_predictor(
    player_id: int,
    *args,
    **kwargs,
) -> int:
    player = Player.objects.get(pk=player_id)
    soundscapes = [sound for sound in player.library.filter(type="Soundscape")]
    instrumentals = [sound for sound in player.library.filter(type="Instrumental")]

    layers: list[SoundLayer] = [
        sound.asLayer(with_gain=random.uniform(0.5, 1.0))
        for sound in random.sample(
            soundscapes,
            min(3, len(soundscapes)),
        )
    ]

    layers += [
        sound.asLayer(with_gain=random.uniform(0.1, 0.5))
        for sound in random.sample(
            instrumentals,
            min(1, len(instrumentals)),
        )
    ]
    cosound = None if not layers else Cosound(layers=layers)

    if cosound:
        player.playing = cosound
        player.save()
        print(f"Now Playing at \033[1m{player.name}\033[22m:")
        print(player.summary())
    else:
        print(f"No New Prediction for \033[1m{player.name}\033[22m")
    return 1 if cosound else 0
