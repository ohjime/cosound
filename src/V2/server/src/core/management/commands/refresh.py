import time
import sys
import logging
from typing import cast
from django.core.management.base import BaseCommand
from core.models import Cosound, Player
from config import settings
from django.utils.module_loading import import_string


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("args", nargs="*")

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("Initializing Cosound Generation Scheduler...")
        )
        predictor_path = getattr(
            settings,
            "COSOUND_CORE_PREDICTION_FUNCTION",
            "core.predict.random_cosound",
        )
        try:
            predictor = import_string(predictor_path)
        except ImportError as e:
            raise ImportError(
                f"Cosound Core: Could not import prediction model '{predictor_path}': {e}"
            )

        try:
            while True:
                self.stdout.write(
                    self.style.SUCCESS(f"\033[1mRefreshing All Players\033[22m")
                )
                players = Player.objects.all()
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
                time.sleep(180)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nScheduler stopped by user."))
            sys.exit(0)
