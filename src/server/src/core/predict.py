import random

from django.db import transaction
from django.tasks import task
from django.utils import timezone

from core.models import PlaybackExposure, Player, Prediction
from core.prediction.live import run_stable_prediction


def _predict_for_player(player_id: int) -> int:
    """Run the existing random predictor.

    Keep this behavior available as the default and rollback path while the
    stable predictor is evaluated.
    """
    with transaction.atomic():
        player = Player.objects.select_for_update().get(pk=player_id)
        library = player.library()
        next_prediction = Prediction.new()

        if library:
            for sound in random.sample(library, k=min(3, len(library))):
                next_prediction.add_layer(
                    sound_id=sound.pk,
                    gain=random.uniform(0.0, 1.0),
                )

        current_exposure = player.current_exposure
        if current_exposure is not None and current_exposure.ended_at is None:
            current_exposure.ended_at = timezone.now()
            current_exposure.status = PlaybackExposure.ENDED
            current_exposure.save(
                update_fields=["ended_at", "status", "updated_at"]
            )
        player.playing = next_prediction
        player.current_exposure = None
        player.save(update_fields=["playing", "current_exposure"])

    if next_prediction:
        player.announce(next_prediction)
        return 1
    return 0


def _stable_predict_for_player(player_id: int) -> int:
    return run_stable_prediction(player_id)


@task
def random_predictor(
    player_id: int,
    *args,
    **kwargs,
) -> int:
    return _predict_for_player(player_id)


@task
def stable_preference_predictor(
    player_id: int,
    *args,
    **kwargs,
) -> int:
    return _stable_predict_for_player(player_id)
