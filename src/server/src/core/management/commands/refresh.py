import sys
import time
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from core.models import Player
from core.predict import Algorithm


REFRESH_INTERVAL_SECONDS = 30


def _get_predictor() -> Any:
    """Resolve the configured predictor and fail clearly on an invalid path.

    Silently falling back on ImportError meant a typo in the setting looked
    like the algorithm simply behaving oddly, which is an expensive thing to
    debug from the sound in the room.
    """
    try:
        return Algorithm.configured_predictor()
    except ImproperlyConfigured as error:
        raise CommandError(str(error)) from error


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
