"""Django adapter and persistence for the Stable Preference Mixer."""

import json
import logging
import random
import secrets
from dataclasses import asdict
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import AlgorithmDecision, PlaybackExposure, Player, Prediction
from core.prediction.domain import (
    ListenerEvidence,
    Mix,
    MixLayer,
    SoundEvidence,
    VoteEvidence,
)
from core.prediction.selector import SelectionConfig, select_mix


logger = logging.getLogger("core.predict")
STABLE_POLICY_VERSION = "stable-preference-mixer-v1"
TRACE_SCHEMA_VERSION = "1"
FEATURE_VERSION = "current-collection-tags-and-exact-mix-votes-v1"
SCORING_VERSION = "tag-prior-beta-update-mean-disagreement-v1"
CANDIDATE_VERSION = "subsets-up-to-3-equal-power-v1"


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


def _legacy_vote_mix_key(vote) -> str | None:
    """Map a rounded stored Cosound to this policy's fixed-gain candidate.

    Historical random-gain votes have uncertain gain attribution. Matching by
    sound set is an explicit legacy approximation; newly attributed votes use
    the exact exposure key instead.
    """
    sound_ids = sorted(
        layer.sound_id for layer in vote.cosound.soundlayer_set.all()
    )
    if not sound_ids or len(sound_ids) > 3 or len(sound_ids) != len(set(sound_ids)):
        return None
    gain = 1 / (len(sound_ids) ** 0.5)
    return Mix(
        tuple(MixLayer(sound_id=sound_id, gain=gain) for sound_id in sound_ids)
    ).key


def _stable_config() -> SelectionConfig:
    house_sound_id = getattr(settings, "COSOUND_HOUSE_SOUND_ID", 5)
    return SelectionConfig(
        min_layers=int(getattr(settings, "COSOUND_MIN_LAYERS", 1)),
        max_layers=int(getattr(settings, "COSOUND_MAX_LAYERS", 3)),
        disagreement_penalty=float(
            getattr(settings, "COSOUND_DISAGREEMENT_PENALTY", 0.25)
        ),
        hold_seconds=int(getattr(settings, "COSOUND_MINIMUM_HOLD_SECONDS", 120)),
        maximum_stay_seconds=getattr(settings, "COSOUND_MAX_STAY_SECONDS", None),
        exploration_probability=float(
            getattr(settings, "COSOUND_EXPLORATION_PROBABILITY", 0.0)
        ),
        exploration_size=int(getattr(settings, "COSOUND_EXPLORATION_SIZE", 5)),
        house_sound_id=int(house_sound_id) if house_sound_id is not None else None,
    )


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
    if result.reason == "retained_no_active_listeners":
        return "Kept the valid current mix because no active listeners were observed."
    if result.reason == "house_mix_no_active_listeners":
        return (
            "Selected the configured house sound because no active listeners or "
            "valid current mix were available."
        )
    if result.reason == "no_active_listener_fallback":
        return (
            "Returned no mix because there were no active listeners, no valid "
            "current mix, and no available house sound."
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


def _listener_evidence(player, decision_time):
    from core.models import Listener
    from vote.models import Vote

    active_cutoff = decision_time - timedelta(
        minutes=int(getattr(settings, "COSOUND_ACTIVE_LISTENER_MINUTES", 5))
    )
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
            mix_key = _legacy_vote_mix_key(vote)
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
            getattr(settings, "COSOUND_ACTIVE_LISTENER_MINUTES", 5)
        )
        * 60,
        "collection_semantics": "current_collection_snapshot",
        "listeners": [
            _profile_snapshot(listener, evidence_by_listener_id[listener.pk])
            for listener in listeners
        ],
        "legacy_sound_set_vote_count": legacy_vote_count,
        "rejected_vote_count": rejected_vote_count,
    }
    return active_listener_ids, evidence, snapshot


def run_stable_prediction(player_id: int) -> int:
    decision_time = timezone.now()
    config = _stable_config()
    exploration_seed = (
        secrets.randbits(64) if config.exploration_probability > 0 else None
    )
    prediction_to_announce = None

    try:
        with transaction.atomic():
            player = Player.objects.select_for_update().get(pk=player_id)
            library = list(player.sounds.prefetch_related("tags").order_by("pk"))
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
                    current_exposure.ended_at = decision_time
                    current_exposure.status = PlaybackExposure.ENDED
                    current_exposure.save(
                        update_fields=["ended_at", "status", "updated_at"]
                    )
                current_exposure = None
            last_change_at = None
            if (
                current_mix is not None
                and current_exposure is not None
                and current_exposure.mix_key == current_mix.key
                and current_exposure.ended_at is None
            ):
                last_change_at = (
                    current_exposure.estimated_audible_at
                    or current_exposure.acknowledged_at
                    or current_exposure.commanded_at
                )

            active_listener_ids, listeners, listener_snapshot = _listener_evidence(
                player,
                decision_time,
            )
            result = select_mix(
                sounds=sounds,
                listeners=listeners,
                current_mix=current_mix,
                last_change_at=last_change_at,
                decision_time=decision_time,
                config=config,
                rng=random.Random(exploration_seed),
            )
            trace = result.as_dict(top=config.exploration_size)
            trace["schema_version"] = TRACE_SCHEMA_VERSION
            trace["policy_version"] = STABLE_POLICY_VERSION
            trace["feature_version"] = FEATURE_VERSION
            trace["scoring_version"] = SCORING_VERSION
            trace["candidate_version"] = CANDIDATE_VERSION
            trace["decision_time"] = decision_time.isoformat()
            trace["evidence_cutoff"] = decision_time.isoformat()
            trace["previous_mix_key"] = current_mix.key if current_mix else None
            trace["last_change_at"] = (
                last_change_at.isoformat() if last_change_at is not None else None
            )
            trace["exploration_seed"] = exploration_seed
            trace["active_exposure_id"] = (
                str(current_exposure.exposure_id) if current_exposure else None
            )
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
            decision = AlgorithmDecision.objects.create(
                player=player,
                policy_version=STABLE_POLICY_VERSION,
                configuration=asdict(config),
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
                    current_exposure.ended_at = decision_time
                    current_exposure.status = PlaybackExposure.ENDED
                    current_exposure.save(
                        update_fields=["ended_at", "status", "updated_at"]
                    )

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
                player.save(update_fields=["playing", "current_exposure"])
                current_exposure = next_exposure
                prediction_to_announce = next_prediction if next_prediction else None
            elif result.selected_mix is not None and current_exposure is None:
                current_exposure = PlaybackExposure.objects.create(
                    player=player,
                    opening_decision=decision,
                    mix_key=result.selected_mix.key,
                    layers=result.selected_mix.as_layers(),
                    commanded_at=decision_time,
                )
                player.current_exposure = current_exposure
                player.save(update_fields=["current_exposure"])
            elif result.selected_mix is None and stored_exposure is not None:
                player.current_exposure = None
                player.save(update_fields=["current_exposure"])

            active_exposure = player.current_exposure or current_exposure
            trace["active_exposure_id"] = (
                str(active_exposure.exposure_id) if active_exposure else None
            )
            trace["decision_id"] = str(decision.decision_id)
            decision.trace = trace
            decision.save(update_fields=["trace"])
    except Exception as error:
        logger.exception(
            "Stable predictor failed for player %s; existing playback was retained",
            player_id,
        )
        try:
            player = Player.objects.get(pk=player_id)
            AlgorithmDecision.objects.create(
                player=player,
                policy_version=STABLE_POLICY_VERSION,
                configuration=asdict(config),
                decided_at=decision_time,
                previous_layers=[
                    {
                        "sound_id": layer.sound_id,
                        "sound_gain": layer.sound_gain,
                    }
                    for layer in player.playing.layers
                ],
                selected_layers=[],
                outcome="error",
                selected_action_probability=0.0,
                trace={
                    "policy_version": STABLE_POLICY_VERSION,
                    "reason": "error",
                    "error_type": type(error).__name__,
                },
            )
        except Exception:
            logger.exception(
                "Could not persist stable predictor failure for player %s",
                player_id,
            )
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
