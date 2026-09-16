"""Django adapter and persistence for the Stable Preference Mixer.

The selector itself is pure (see ``selector.py``). This module is everything
around it: reading a player's evidence, deciding whether the player should be
predicting for at all, and committing the result.

Three things here differ from a naive wiring, and each is deliberate:

* **The lifecycle gate runs first.** Sleeping and inactivity are this project's
  concepts, not the selector's, and the selector would happily keep a dead room
  playing forever. ``_lifecycle_gate`` reproduces the behaviour the dummy
  predictor had, and only then is a mix chosen.
* **Selection happens outside the player row lock.** ``vote.views.submit_vote``
  locks the same row, so time spent scoring is time a listener's vote spends
  waiting. We snapshot under a short lock, score unlocked, then re-validate and
  commit under a second short lock.
* **A decision is recorded even when nothing changes.** A hold and a failure
  both write an ``AlgorithmDecision``; that is the point of the log. The one
  gap is the lifecycle gate, which returns before a decision exists — a room
  falling silent for inactivity is a lifecycle event, not a choice the
  selector made.
"""

import json
import logging
import random
import secrets
from dataclasses import asdict
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.models import (
    AlgorithmDecision,
    PlayerProgram,
    PlaybackExposure,
    Player,
    Prediction,
)
from core.predict import AWAKEN_INTENT, PREDICTION_RETRY, REFRESH_INTENT
from core.prediction.domain import (
    ListenerEvidence,
    Mix,
    MixLayer,
    SoundEvidence,
    VoteEvidence,
)
from core.prediction.selector import SelectionConfig, select_mix


logger = logging.getLogger("core.predict")
STABLE_POLICY_VERSION = "stable-preference-mixer-v2"
TRACE_SCHEMA_VERSION = "1"
FEATURE_VERSION = "current-collection-tags-and-exact-mix-votes-v1"
SCORING_VERSION = "tag-prior-beta-update-mean-disagreement-v1"
CANDIDATE_VERSION = "configured-equal-power-subsets-v2"


def _activity_window(program: PlayerProgram) -> timedelta:
    return timedelta(minutes=program.algorithm_active_listener_minutes)


def _sleep_window(program: PlayerProgram) -> timedelta:
    return timedelta(minutes=program.algorithm_sleep_after_minutes)


def _mix_from_prediction(prediction: Prediction) -> Mix | None:
    layers = tuple(
        MixLayer(sound_id=layer.sound_id, gain=layer.sound_gain)
        for layer in prediction.layers
        if layer.sound_gain > 0
    )
    return Mix(layers) if layers else None


def _prediction_from_mix(mix: Mix | None) -> Prediction:
    prediction = Prediction.new()
    if mix is not None:
        for layer in mix.layers:
            prediction.add_layer(layer.sound_id, layer.gain)
    return prediction


def _sound_evidence(sound) -> SoundEvidence:
    return SoundEvidence(
        sound_id=sound.pk,
        tags=tuple(tag.name for tag in sound.tags.all()),
    )


def _legacy_vote_mix_key(vote, max_layers: int) -> str | None:
    """Map a rounded stored Cosound to this policy's fixed-gain candidate.

    Historical random-gain votes have uncertain gain attribution, and a stored
    Cosound rounds gains up onto a 0.05 grid, so its gains never equal a mix
    key's anyway. Matching by sound set is an explicit legacy approximation;
    newly attributed votes use the exact exposure key instead.
    """
    sound_ids = sorted(
        layer.sound_id for layer in vote.cosound.soundlayer_set.all()
    )
    if (
        not sound_ids
        or len(sound_ids) > max_layers
        or len(sound_ids) != len(set(sound_ids))
    ):
        return None
    gain = 1 / (len(sound_ids) ** 0.5)
    return Mix(
        tuple(MixLayer(sound_id=sound_id, gain=gain) for sound_id in sound_ids)
    ).key


def _stable_config(program: PlayerProgram) -> SelectionConfig:
    """Build the running policy from this post's admin-managed parameters."""
    return SelectionConfig(
        min_layers=program.algorithm_min_layers,
        max_layers=program.algorithm_max_layers,
        disagreement_penalty=program.algorithm_disagreement_penalty,
        hold_seconds=program.algorithm_minimum_hold_seconds,
        maximum_stay_seconds=program.algorithm_maximum_stay_seconds,
        exploration_probability=program.algorithm_exploration_probability,
        exploration_size=program.algorithm_exploration_size,
        baseline_sound_id=program.baseline_id,
    )


def _configuration_snapshot(
    program: PlayerProgram,
    config: SelectionConfig,
) -> dict:
    """Return every post parameter that shaped or scheduled this decision."""
    return {
        **asdict(config),
        "active_listener_minutes": program.algorithm_active_listener_minutes,
        "sleep_after_minutes": program.algorithm_sleep_after_minutes,
        "refresh_interval_seconds": program.algorithm_refresh_interval_seconds,
    }


def _profile_snapshot(listener, evidence: ListenerEvidence) -> dict:
    vote_counts: dict[str, dict[str, int]] = {}
    for vote in evidence.votes:
        counts = vote_counts.setdefault(vote.mix_key, {"positive": 0, "total": 0})
        counts["positive"] += int(vote.positive)
        counts["total"] += 1
    return {
        "listener_id": listener.pk,
        "saved_sounds": [
            {"sound_id": sound.sound_id, "tags": list(sound.tags)}
            for sound in evidence.saved_sounds
        ],
        "vote_counts_by_mix": vote_counts,
    }


def _explain_selection(result, listeners, config: SelectionConfig) -> str:
    listener_count = len(listeners)
    if result.reason == "minimum_hold":
        return (
            f"Kept the current mix because it has not completed the configured "
            f"{config.hold_seconds}-second minimum hold."
        )
    if result.reason == "maximum_stay":
        return (
            "Changed the sound set by one permitted layer edit because the "
            f"current mix reached its {config.maximum_stay_seconds}-second "
            f"maximum stay. It was the highest-scoring alternative among "
            f"{result.reachable_count} reachable choices."
        )
    if result.reason == "maximum_stay_unavailable":
        return (
            "Kept the current mix after its maximum stay because this player "
            "had no alternative that could change a sound within one layer edit."
        )
    if result.reason == "baseline_no_active_listeners":
        return (
            "Selected the post's configured baseline because no active listeners "
            "were observed."
        )
    if result.reason == "silent_no_active_listeners":
        return (
            "Returned silence because no active listeners or baseline were "
            "available."
        )
    if result.reason == "no_feasible_mix":
        return "Returned no mix because this player has no available candidate sounds."
    if result.selected_mix is None or result.selected_score is None:
        return f"Completed the decision with outcome {result.reason}."

    exact_vote_count = sum(
        vote.mix_key == result.selected_mix.key
        for listener in listeners
        for vote in listener.votes
    )
    selection_kind = "Exploration selected" if result.explored else "Selected"
    return (
        f"{selection_kind} this mix after weighting {listener_count} active "
        f"listener{'s' if listener_count != 1 else ''} equally. Saved-sound "
        f"tags supplied weak prior evidence and {exact_vote_count} prior "
        f"vote{'s' if exact_vote_count != 1 else ''} applied to this exact mix. "
        f"Its group score was {result.selected_score.group_score:.3f} "
        f"(mean {result.selected_score.mean:.3f}, disagreement "
        f"{result.selected_score.disagreement:.3f}) among "
        f"{result.reachable_count} reachable choices."
    )


def _listener_evidence(
    player,
    program,
    decision_time,
    requesting_listener_id=None,
):
    from core.models import Listener
    from vote.models import Vote

    active_cutoff = decision_time - _activity_window(program)
    active_listener_ids = list(
        Vote.objects.filter(
            player=player,
            created_at__gte=active_cutoff,
            created_at__lte=decision_time,
        )
        .order_by("voter_id")
        .values_list("voter_id", flat=True)
        .distinct()
    )
    if (
        requesting_listener_id is not None
        and requesting_listener_id not in active_listener_ids
    ):
        # Someone asking to wake the room is present by definition, even though
        # the tap itself cast no vote. They contribute saved-sound tags and no
        # votes, which is exactly the weak evidence the prior is built for. The
        # decision records them among active_listener_ids, so the log still
        # says who the choice was made for.
        active_listener_ids = sorted(active_listener_ids + [requesting_listener_id])
    listeners = list(
        Listener.objects.filter(pk__in=active_listener_ids)
        .prefetch_related("collection__tags")
        .order_by("pk")
    )
    votes = list(
        Vote.objects.filter(
            player=player,
            voter_id__in=active_listener_ids,
            created_at__lte=decision_time,
        )
        .select_related("exposure", "cosound")
        .prefetch_related("cosound__soundlayer_set")
        .order_by("created_at", "pk")
    )
    votes_by_listener: dict[int, list[VoteEvidence]] = {
        listener.pk: [] for listener in listeners
    }
    legacy_vote_count = 0
    rejected_vote_count = 0
    for vote in votes:
        if vote.value == 1:
            positive = True
        elif vote.value in (0, -1):
            positive = False
        else:
            rejected_vote_count += 1
            continue
        if vote.exposure_id and vote.exposure.player_id == player.pk:
            mix_key = vote.exposure.mix_key
        elif vote.exposure_id:
            rejected_vote_count += 1
            continue
        else:
            mix_key = _legacy_vote_mix_key(vote, program.algorithm_max_layers)
            legacy_vote_count += 1
        if mix_key:
            votes_by_listener[vote.voter_id].append(
                VoteEvidence(mix_key=mix_key, positive=positive)
            )

    evidence = tuple(
        ListenerEvidence(
            listener_key=str(listener.pk),
            saved_sounds=tuple(
                _sound_evidence(sound)
                for sound in sorted(listener.collection.all(), key=lambda item: item.pk)
            ),
            votes=tuple(votes_by_listener[listener.pk]),
        )
        for listener in listeners
    )
    evidence_by_listener_id = {
        int(listener.listener_key): listener for listener in evidence
    }
    snapshot = {
        "active_listener_window_seconds": int(
            _activity_window(program).total_seconds()
        ),
        "collection_semantics": "current_collection_snapshot",
        "listeners": [
            _profile_snapshot(listener, evidence_by_listener_id[listener.pk])
            for listener in listeners
        ],
        "legacy_sound_set_vote_count": legacy_vote_count,
        "rejected_vote_count": rejected_vote_count,
    }
    return active_listener_ids, evidence, snapshot


def _close_exposure(exposure, when) -> None:
    exposure.ended_at = when
    exposure.status = PlaybackExposure.ENDED
    exposure.save(update_fields=["ended_at", "status", "updated_at"])


def _set_current_exposure_quietly(player, exposure) -> None:
    """Repoint ``current_exposure`` without waking every connected client.

    A plain ``save()`` fires ``post_save``, which publishes ``player.changed``
    and makes the player re-fetch and re-evaluate its mix. That is right when
    the mix actually changed; here it has not — we are only recording which
    exposure covers what is already playing — so the notification would be a
    round trip for nothing.
    """
    Player.objects.filter(pk=player.pk).update(current_exposure=exposure)
    player.current_exposure = exposure


def _lifecycle_gate(player, program, decision_time):
    """Apply sleep/inactivity rules before the stable selector runs.

    Returns ``None`` to continue on to selection, or an int to return straight
    out of the task. Listener relevance has a shorter window than room
    lifetime, so stale listeners stop shaping mixes before the room sleeps.
    """
    from vote.models import Vote

    if player.sleeping:
        return 0

    activity_window = _activity_window(program)
    recent_votes = Vote.recent(
        player,
        minutes=int(activity_window.total_seconds() // 60),
    )
    if not recent_votes:
        # Listener relevance and room lifetime are deliberately separate. A
        # room can remain awake after its listeners age out of scoring without
        # letting their stale preferences influence every new mix.
        sleep_cutoff = decision_time - _sleep_window(program)
        recently_activated = bool(
            player.activated_at is not None
            and player.activated_at >= sleep_cutoff
        )
        recently_voted = Vote.objects.filter(
            player=player,
            created_at__gte=sleep_cutoff,
            created_at__lte=decision_time,
        ).exists()
        if player.playing and (recently_activated or recently_voted):
            return None
        current_exposure = player.current_exposure
        if current_exposure is not None and current_exposure.ended_at is None:
            _close_exposure(current_exposure, decision_time)
        player.playing = Prediction.new()
        player.current_exposure = None
        player.save(update_fields=["playing", "current_exposure"])
        return 0
    return None


def _record_error(player_id, configuration, decision_time, intent, error) -> None:
    try:
        player = Player.objects.get(pk=player_id)
        AlgorithmDecision.objects.create(
            player=player,
            policy_version=STABLE_POLICY_VERSION,
            configuration=configuration,
            decided_at=decision_time,
            previous_layers=[
                {"sound_id": layer.sound_id, "sound_gain": layer.sound_gain}
                for layer in player.playing.layers
            ],
            selected_layers=[],
            outcome="error",
            selected_action_probability=0.0,
            trace={
                "policy_version": STABLE_POLICY_VERSION,
                "reason": "error",
                "intent": intent,
                "error_type": type(error).__name__,
            },
        )
    except Exception:
        logger.exception(
            "Could not persist stable predictor failure for player %s",
            player_id,
        )


def run_stable_prediction(
    player_id: int,
    *,
    intent: str = REFRESH_INTENT,
    requesting_listener_id: int | None = None,
) -> int:
    if intent not in {REFRESH_INTENT, AWAKEN_INTENT}:
        raise ValueError(f"Unknown prediction intent: {intent!r}")
    awakening = intent == AWAKEN_INTENT
    decision_time = timezone.now()
    config = None
    configuration = {}
    exploration_seed = None
    prediction_to_announce = None

    try:
        # --- Phase 1: gate and snapshot, under a short lock ----------------
        with transaction.atomic():
            player = (
                Player.objects.select_for_update()
                .select_related("program")
                .get(pk=player_id)
            )
            program = player.program
            config = _stable_config(program)
            configuration = _configuration_snapshot(program, config)
            exploration_seed = (
                secrets.randbits(64)
                if config.exploration_probability > 0
                else None
            )
            if not awakening:
                gated = _lifecycle_gate(player, program, decision_time)
                if gated is not None:
                    return gated

            library = list(
                program.collection.prefetch_related("tags").order_by("pk")
            )
            program_id = program.pk
            library_ids = tuple(sound.pk for sound in library)
            sounds = tuple(_sound_evidence(sound) for sound in library)
            current_mix = _mix_from_prediction(player.playing)

            stored_exposure = player.current_exposure
            current_exposure = stored_exposure
            if current_exposure is not None and (
                current_exposure.ended_at is not None
                or current_mix is None
                or current_exposure.mix_key != current_mix.key
            ):
                if current_exposure.ended_at is None:
                    _close_exposure(current_exposure, decision_time)
                current_exposure = None

            last_change_at = None
            if (
                current_mix is not None
                and current_exposure is not None
                and current_exposure.mix_key == current_mix.key
                and current_exposure.ended_at is None
            ):
                # No player acknowledgement exists, so in practice this is
                # commanded_at; the other two are kept for when one does.
                last_change_at = (
                    current_exposure.estimated_audible_at
                    or current_exposure.acknowledged_at
                    or current_exposure.commanded_at
                )

            active_listener_ids, listeners, listener_snapshot = _listener_evidence(
                player,
                program,
                decision_time,
                requesting_listener_id,
            )

        # --- Phase 2: score without holding anything ----------------------
        result = select_mix(
            sounds=sounds,
            listeners=listeners,
            current_mix=current_mix,
            last_change_at=last_change_at,
            decision_time=decision_time,
            config=config,
            rng=random.Random(exploration_seed),
            awaken=awakening,
        )

        trace = result.as_dict(top=config.exploration_size)
        trace["schema_version"] = TRACE_SCHEMA_VERSION
        trace["policy_version"] = STABLE_POLICY_VERSION
        trace["feature_version"] = FEATURE_VERSION
        trace["scoring_version"] = SCORING_VERSION
        trace["candidate_version"] = CANDIDATE_VERSION
        trace["decision_time"] = decision_time.isoformat()
        trace["evidence_cutoff"] = decision_time.isoformat()
        trace["intent"] = intent
        trace["previous_mix_key"] = current_mix.key if current_mix else None
        trace["last_change_at"] = (
            last_change_at.isoformat() if last_change_at is not None else None
        )
        trace["exploration_seed"] = exploration_seed
        trace["explanation"] = _explain_selection(result, listeners, config)
        trace["candidate_manifest"] = {
            "source": "input_snapshot.library",
            "candidate_count": result.candidate_count,
            "reachable_count": result.reachable_count,
            "configured_min_layers": config.min_layers,
            "effective_min_layers": (
                min(config.min_layers, len(sounds)) if sounds else None
            ),
            "max_layers": config.max_layers,
        }
        input_snapshot = {
            "library": [
                {"sound_id": sound.sound_id, "tags": list(sound.tags)}
                for sound in sounds
            ],
            **listener_snapshot,
        }

        # --- Phase 3: re-validate and commit, under a second short lock ----
        with transaction.atomic():
            player = (
                Player.objects.select_for_update()
                .select_related("program")
                .get(pk=player_id)
            )

            # A queued task can outlive the awake state that scheduled it, and
            # anything could have changed the mix while we were scoring.
            if not awakening and player.sleeping:
                return 0
            if player.program_id != program_id:
                logger.info(
                    "Discarded a stable decision for player %s: the player program "
                    "changed while it was being scored",
                    player_id,
                )
                return PREDICTION_RETRY if awakening else 0
            committed_program = player.program
            committed_config = _stable_config(committed_program)
            if (
                _configuration_snapshot(committed_program, committed_config)
                != configuration
            ):
                logger.info(
                    "Discarded a stable decision for player %s: its algorithm "
                    "parameters changed while it was being scored",
                    player_id,
                )
                return PREDICTION_RETRY if awakening else 0
            committed_mix = _mix_from_prediction(player.playing)
            if (committed_mix.key if committed_mix else None) != (
                current_mix.key if current_mix else None
            ):
                logger.info(
                    "Discarded a stable decision for player %s: the mix changed "
                    "while it was being scored",
                    player_id,
                )
                return PREDICTION_RETRY if awakening else 0
            committed_library_ids = tuple(
                committed_program.collection.select_for_update()
                .order_by("pk")
                .values_list("pk", flat=True)
            )
            if committed_library_ids != library_ids:
                logger.info(
                    "Discarded a stable decision for player %s: the sound library "
                    "changed while it was being scored",
                    player_id,
                )
                return PREDICTION_RETRY if awakening else 0

            current_exposure = player.current_exposure
            if current_exposure is not None and current_exposure.ended_at is not None:
                current_exposure = None

            decision = AlgorithmDecision.objects.create(
                player=player,
                policy_version=STABLE_POLICY_VERSION,
                configuration=configuration,
                decided_at=decision_time,
                previous_layers=current_mix.as_layers() if current_mix else [],
                selected_layers=(
                    result.selected_mix.as_layers() if result.selected_mix else []
                ),
                active_listener_ids=active_listener_ids,
                input_snapshot=input_snapshot,
                outcome=result.reason,
                selected_score=(
                    result.selected_score.group_score
                    if result.selected_score is not None
                    else None
                ),
                selected_action_probability=result.selected_action_probability,
                exploration=result.explored,
                trace=trace,
            )

            if result.changed:
                if current_exposure is not None and current_exposure.ended_at is None:
                    _close_exposure(current_exposure, decision_time)

                next_prediction = _prediction_from_mix(result.selected_mix)
                next_exposure = None
                if result.selected_mix is not None:
                    next_exposure = PlaybackExposure.objects.create(
                        player=player,
                        opening_decision=decision,
                        mix_key=result.selected_mix.key,
                        layers=result.selected_mix.as_layers(),
                        commanded_at=decision_time,
                    )
                player.playing = next_prediction
                player.current_exposure = next_exposure
                update_fields = ["playing", "current_exposure"]
                if awakening and result.selected_mix is not None:
                    player.activated_at = decision_time
                    update_fields.append("activated_at")
                # The mix really changed, so let post_save publish
                # player.changed and pull every connected client forward.
                player.save(update_fields=update_fields)
                current_exposure = next_exposure
                prediction_to_announce = next_prediction if next_prediction else None
            elif result.selected_mix is not None and current_exposure is None:
                # Adopt an exposure for a mix that is already playing, so the
                # hold clock has something to measure from.
                current_exposure = PlaybackExposure.objects.create(
                    player=player,
                    opening_decision=decision,
                    mix_key=result.selected_mix.key,
                    layers=result.selected_mix.as_layers(),
                    commanded_at=decision_time,
                )
                _set_current_exposure_quietly(player, current_exposure)
            elif result.selected_mix is None and player.current_exposure_id:
                _set_current_exposure_quietly(player, None)

            if awakening and result.selected_mix is not None and not result.changed:
                # A concurrent awaken may already have installed this mix. Mark
                # that committed playback as awake without opening another
                # exposure or announcing the same transition twice.
                player.activated_at = decision_time
                player.save(update_fields=["activated_at"])

            trace["active_exposure_id"] = (
                str(current_exposure.exposure_id) if current_exposure else None
            )
            trace["decision_id"] = str(decision.decision_id)
            decision.trace = trace
            decision.save(update_fields=["trace"])
    except Exception as error:
        logger.exception(
            "Stable predictor failed for player %s; existing playback was retained",
            player_id,
        )
        _record_error(player_id, configuration, decision_time, intent, error)
        return 0

    logger.info(
        "cosound_algorithm_decision %s",
        json.dumps(
            {
                "decision_id": str(decision.decision_id),
                "player_id": player_id,
                **trace,
            },
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ),
    )
    if prediction_to_announce is not None:
        try:
            player.announce(prediction_to_announce)
        except Exception:
            logger.exception(
                "Prediction committed for player %s, but its console "
                "announcement failed",
                player_id,
            )
    return 1 if result.selected_mix else 0
