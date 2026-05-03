import random
from django.tasks import task
from pydantic import BaseModel, Field
from typing import List


class PredictionLayer(BaseModel):
    sound_id: int
    sound_gain: float = Field(default=1.0, ge=0.0, le=1.0)


class Prediction(BaseModel):

    layers: List[PredictionLayer] = Field(default_factory=list)

    def summary(self):
        from core.models import Sound

        response = "Prediction Summary:\n"
        for layer in self.layers:
            try:
                sound = Sound.objects.get(pk=layer.sound_id)
                response += (
                    f"- {sound.title} by {sound.artist} at gain {layer.sound_gain}\n"
                )
            except Sound.DoesNotExist:
                response += f"- Sound ID {layer.sound_id} not found at gain {layer.sound_gain}\n"
        return response


@task
def random_predictor(
    player_id: int,
    *args,
    **kwargs,
) -> int:

    from core.models import Sound, Player

    player = Player.objects.get(pk=player_id)
    soundscapes: list[Sound] = [sound for sound in player.sounds.all()]

    layers = [
        PredictionLayer(
            sound_id=sound.pk,
            sound_gain=round(random.uniform(0.1, 0.4), 2),
        )
        for sound in random.sample(
            soundscapes,
            min(3, len(soundscapes)),
        )
    ]

    prediction = None if not layers else Prediction(layers=layers)

    if prediction:
        player.playing = prediction
        player.save()
        print(f"New Prediction for \033[1m{player.name}\033[22m:")
        print(prediction.summary())
    else:
        print(f"No New Prediction for \033[1m{player.name}\033[22m")
    return 1 if prediction else 0
