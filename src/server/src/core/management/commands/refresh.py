import time
import sys
import logging
from typing import cast, Any
from django.core.management.base import BaseCommand, CommandError
from django.utils.module_loading import import_string
from core.models import Cosound, Player
from django.conf import settings


REFRESH_INTERVAL_SECONDS = 30


def _get_predictor() -> Any:
    """Resolve the configured predictor and fail clearly on an invalid path.

    Silently falling back on ImportError meant a typo in the setting looked
    like the algorithm simply behaving oddly, which is an expensive thing to
    debug from the sound in the room.
    """
    predictor_path = getattr(settings, "COSOUND_CORE_PREDICTOR", None)
    if predictor_path:
        try:
            return import_string(predictor_path)
        except ImportError as error:
            raise CommandError(
                f"Could not import COSOUND_CORE_PREDICTOR={predictor_path!r}"
            ) from error
    # Fallback to core default
    from core.predict import random_predictor

    return random_predictor


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("args", nargs="*")

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Initializing Cosound Generation Scheduler...")
        )
        predictor = _get_predictor()

        try:
            while True:
                self.stdout.write(
                    self.style.SUCCESS(f"\033[1mRefreshing All Players\033[22m")
                )
                players = Player.objects.filter(sleeping=False)
                if players:
                    for player in players:
                        try:
                            prediction = predictor.enqueue(
                                player_id=player.pk,
                            )
                        except (ValueError, Exception) as e:
                            # Log the error but continue processing other players
                            self.stdout.write(
                                self.style.ERROR(
                                    f"Failed to refresh player {player.name}: {str(e)}"
                                )
                            )
                            continue
                else:
                    self.stdout.write(self.style.WARNING("No Active Players Found."))
                time.sleep(REFRESH_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nScheduler stopped by user."))
            sys.exit(0)
