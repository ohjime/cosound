import sys
import time
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django_tasks.exceptions import TaskResultDoesNotExist

from core.models import Player
from core.predict import Algorithm


SCHEDULER_TICK_SECONDS = 1


def _refresh_is_due(player, last_enqueued_at: dict[int, float], now: float) -> bool:
    """Whether this player has reached its independently configured cadence."""
    last_enqueued = last_enqueued_at.get(player.pk)
    return (
        last_enqueued is None
        or now - last_enqueued
        >= player.program.algorithm_refresh_interval_seconds
    )


def _task_is_in_flight(task_result) -> bool:
    """Keep at most one queued or running prediction per player."""
    if task_result is None:
        return False
    try:
        task_result.refresh()
    except TaskResultDoesNotExist:
        return False
    return not task_result.is_finished


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
        last_enqueued_at: dict[int, float] = {}
        task_results = {}

        try:
            while True:
                players = list(
                    Player.objects.filter(sleeping=False).select_related("program")
                )
                active_ids = {player.pk for player in players}
                last_enqueued_at = {
                    player_id: enqueued_at
                    for player_id, enqueued_at in last_enqueued_at.items()
                    if player_id in active_ids
                }
                task_results = {
                    player_id: task_result
                    for player_id, task_result in task_results.items()
                    if player_id in active_ids
                }
                now = time.monotonic()
                due_players = [
                    player
                    for player in players
                    if _refresh_is_due(player, last_enqueued_at, now)
                ]
                players_to_enqueue = [
                    player
                    for player in due_players
                    if not _task_is_in_flight(task_results.get(player.pk))
                ]

                if players_to_enqueue:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "\033[1mRefreshing "
                            f"{len(players_to_enqueue)} Player(s)\033[22m"
                        )
                    )
                for player in players_to_enqueue:
                    # Record attempts as well as successful enqueues. A broken
                    # queue should respect the player's cadence instead of
                    # retrying on every one-second scheduler tick.
                    last_enqueued_at[player.pk] = now
                    try:
                        task_results[player.pk] = predictor.enqueue(
                            player_id=player.pk
                        )
                    except Exception as error:
                        self.stdout.write(
                            self.style.ERROR(
                                f"Failed to refresh player {player.name}: {error}"
                            )
                        )

                time.sleep(SCHEDULER_TICK_SECONDS)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nScheduler stopped by user."))
            sys.exit(0)
