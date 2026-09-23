import random
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.tasks import task
from django.utils import timezone
from django.utils.module_loading import import_string

from core.models import Listener, ListenerPresence, PlaybackExposure, Player, Prediction, Sound
from vote.models import Vote


REFRESH_INTENT = "refresh"
AWAKEN_INTENT = "awaken"
PREDICTION_RETRY = -1


def _end_current_exposure(player: Player, when) -> None:
    """Close stable-mixer attribution before the legacy policy takes over."""
    if player.current_exposure_id is None:
        return
    exposure = (
        PlaybackExposure.objects.select_for_update()
        .filter(pk=player.current_exposure_id)
        .first()
    )
    if exposure is not None and exposure.ended_at is None:
        exposure.ended_at = when
        exposure.status = PlaybackExposure.ENDED
        exposure.save(update_fields=["ended_at", "status", "updated_at"])
    player.current_exposure = None


def _predict_for_player(player_id: int, *, intent: str = REFRESH_INTENT) -> int:
    """Run the legacy tag-affinity policy.

    Awakening belongs to the selected policy too. Keeping the legacy bootstrap
    here means the rollback switch still changes the whole algorithm rather
    than leaving request-time activation permanently coupled to the stable
    mixer.
    """
    if intent not in {REFRESH_INTENT, AWAKEN_INTENT}:
        raise ValueError(f"Unknown prediction intent: {intent!r}")

    prediction_to_announce = None
    with transaction.atomic():
        player = (
            Player.objects.select_for_update()
            .select_related("program")
            .get(pk=player_id)
        )

        if intent == AWAKEN_INTENT:
            sound_ids = list(
                player.program.collection.published()
                .select_for_update()
                .order_by("pk")
                .values_list("pk", flat=True)
            )
            available_ids = set(sound_ids)
            current_layers = list(player.playing.layers)
            current_ids = [layer.sound_id for layer in current_layers]
            if (
                not player.sleeping
                and current_ids
                and all(layer.sound_gain > 0 for layer in current_layers)
                and len(current_ids) == len(set(current_ids))
                and set(current_ids) <= available_ids
            ):
                player.activated_at = timezone.now()
                player.save(update_fields=["activated_at"])
                return 1
            if not sound_ids:
                _end_current_exposure(player, timezone.now())
                player.playing = Prediction.new()
                player.save(update_fields=["playing", "current_exposure"])
                return 0

            decision_time = timezone.now()
            _end_current_exposure(player, decision_time)
            prediction_to_announce = Prediction.new()
            prediction_to_announce.add_layer(
                sound_id=random.choice(sound_ids),
                gain=1.0,
            )
            player.playing = prediction_to_announce
            player.activated_at = decision_time
            player.save(
                update_fields=["playing", "current_exposure", "activated_at"]
            )

        elif player.sleeping:
            return 0
        else:
            program = player.program
            activity_window = timedelta(
                minutes=program.algorithm_active_listener_minutes
            )
            recent_votes = Vote.recent(
                player,
                minutes=int(activity_window.total_seconds() // 60),
            )
            recent_visits = ListenerPresence.objects.filter(
                player=player,
                visited_at__gte=timezone.now() - activity_window,
            )
            if not recent_votes and not recent_visits.exists():
                decision_time = timezone.now()
                sleep_cutoff = decision_time - timedelta(
                    minutes=program.algorithm_sleep_after_minutes
                )
                recently_activated = bool(
                    player.activated_at is not None
                    and player.activated_at >= sleep_cutoff
                )
                recently_voted = Vote.objects.filter(
                    player=player,
                    created_at__gte=sleep_cutoff,
                    created_at__lte=decision_time,
                ).exists()
                recently_visited = ListenerPresence.objects.filter(
                    player=player, visited_at__gte=sleep_cutoff,
                ).exists()
                if player.playing and (recently_activated or recently_voted or recently_visited):
                    return 0
                _end_current_exposure(player, decision_time)
                player.playing = Prediction.new()
                player.save(update_fields=["playing", "current_exposure"])
                return 0

            active_ids = {vote.voter_id for vote in recent_votes}
            active_ids.update(recent_visits.values_list("listener_id", flat=True))
            active_listeners = Listener.objects.filter(pk__in=active_ids).order_by("pk")
            next_prediction = Prediction.new()
            selected_sound_ids: set[int] = set()

            library_by_tag: dict[int, list[Sound]] = defaultdict(list)
            for sound in program.collection.published().prefetch_related("tags"):
                for tag in sound.tags.all():
                    library_by_tag[tag.pk].append(sound)

            for listener in active_listeners:
                tag_counts: Counter[int] = Counter()
                for sound in listener.collection.prefetch_related("tags"):
                    tag_counts.update(tag.pk for tag in sound.tags.all())

                if not tag_counts:
                    continue

                highest_count = max(tag_counts.values())
                usable_top_tags = [
                    tag_id
                    for tag_id, count in tag_counts.items()
                    if count == highest_count and library_by_tag[tag_id]
                ]
                if not usable_top_tags:
                    continue

                selected_tag = random.choice(usable_top_tags)
                unused_sounds = [
                    sound
                    for sound in library_by_tag[selected_tag]
                    if sound.pk not in selected_sound_ids
                ]
                if not unused_sounds:
                    continue

                selected_sound = random.choice(unused_sounds)
                next_prediction.add_layer(sound_id=selected_sound.pk, gain=1.0)
                selected_sound_ids.add(selected_sound.pk)

            if next_prediction:
                _end_current_exposure(player, timezone.now())
                player.playing = next_prediction
                player.save(update_fields=["playing", "current_exposure"])
                prediction_to_announce = next_prediction

    if prediction_to_announce is not None:
        player.announce(prediction_to_announce)
        return 1
    return 0


@task
def random_predictor(
    player_id: int,
    *args,
    **kwargs,
) -> int:
    """The tag-affinity predictor this project ran before the stable mixer.

    Kept registered as the rollback path: setting
    ``COSOUND_CORE_PREDICTOR=core.predict.random_predictor`` restores it
    without a deploy of new code.
    """
    return _predict_for_player(
        player_id,
        intent=kwargs.pop("intent", REFRESH_INTENT),
    )


@task
def stable_preference_predictor(
    player_id: int,
    *args,
    **kwargs,
) -> int:
    """The default predictor. See ``core.prediction`` for the policy."""
    # Imported here so that core.predict stays importable during migrations,
    # which reference it for historical Prediction fields.
    from core.prediction.live import run_stable_prediction

    return run_stable_prediction(
        player_id,
        intent=kwargs.pop("intent", REFRESH_INTENT),
        requesting_listener_id=kwargs.pop("listener_id", None),
    )


class Algorithm:
    """Facade for the policy selected in Django settings.

    Both scheduled refreshes and synchronous wake-ups resolve the same task, so
    the rollback switch cannot silently produce one policy in the scheduler and
    another one in the request path.
    """

    @staticmethod
    def configured_predictor() -> Any:
        predictor_path = getattr(settings, "COSOUND_CORE_PREDICTOR", None)
        if not predictor_path:
            return random_predictor
        try:
            return import_string(predictor_path)
        except ImportError as error:
            raise ImproperlyConfigured(
                f"Could not import COSOUND_CORE_PREDICTOR={predictor_path!r}"
            ) from error

    @classmethod
    def awaken(cls, player: Player, listener=None) -> Prediction | None:
        """Synchronously resume the configured policy for ``player``.

        ``listener`` is whoever asked for the activation, when a request can
        name them. A tap that wakes a resting room casts no vote — there is no
        mix yet to have an opinion about. Naming them lets the policy treat the
        requester as active and weigh their saved sounds; without a requester,
        the Player Program's baseline-or-silence fallback applies. Policies that
        have no use for the listener ignore the argument.
        """
        if player.pk is None:
            raise ValueError("Cannot awaken an unsaved player")
        predictor = cls.configured_predictor()
        for attempt in range(2):
            try:
                completed = predictor.call(
                    player_id=player.pk,
                    intent=AWAKEN_INTENT,
                    listener_id=listener.pk if listener is not None else None,
                )
            except Player.DoesNotExist:
                return None
            try:
                player.refresh_from_db()
            except Player.DoesNotExist:
                return None

            layers = list(player.playing.layers)
            playable_ids = [
                layer.sound_id for layer in layers if layer.sound_gain > 0
            ]
            prediction_is_playable = bool(
                not player.sleeping
                and playable_ids
                and len(playable_ids) == len(layers)
                and len(playable_ids) == len(set(playable_ids))
                and player.program.collection.published()
                .filter(pk__in=playable_ids)
                .count()
                == len(playable_ids)
            )
            if completed == 1 and prediction_is_playable:
                return player.playing
            if completed == PREDICTION_RETRY and attempt == 0:
                # The stable policy deliberately discards a decision if the
                # mix or library changes between its snapshot and commit. A
                # single retry turns that benign optimistic race into a normal
                # activation without allowing a stale JSON prediction through.
                continue
            return None
        return None
