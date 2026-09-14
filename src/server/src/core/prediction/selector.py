from __future__ import annotations

import itertools
import math
import random
import statistics
from dataclasses import dataclass
from datetime import datetime

from core.prediction.domain import ListenerEvidence, Mix, MixLayer, SoundEvidence


@dataclass(frozen=True)
class SelectionConfig:
    min_layers: int = 1
    max_layers: int = 3
    disagreement_penalty: float = 0.25
    hold_seconds: int = 120
    maximum_stay_seconds: int | None = None
    score_precision: int = 8
    exploration_probability: float = 0.0
    exploration_size: int = 5
    house_sound_id: int | None = 5

    def __post_init__(self) -> None:
        if self.min_layers < 1:
            raise ValueError("min_layers must be at least one")
        if self.max_layers < 1:
            raise ValueError("max_layers must be at least one")
        if self.min_layers > self.max_layers:
            raise ValueError("min_layers cannot exceed max_layers")
        if (
            not math.isfinite(self.disagreement_penalty)
            or self.disagreement_penalty < 0
        ):
            raise ValueError("disagreement_penalty must be finite and nonnegative")
        if self.hold_seconds < 0:
            raise ValueError("hold_seconds cannot be negative")
        if self.maximum_stay_seconds is not None:
            if self.maximum_stay_seconds <= 0:
                raise ValueError("maximum_stay_seconds must be positive or None")
            if self.maximum_stay_seconds < self.hold_seconds:
                raise ValueError(
                    "maximum_stay_seconds cannot be shorter than hold_seconds"
                )
        if not 0 <= self.exploration_probability <= 1:
            raise ValueError("exploration_probability must be in [0, 1]")
        if self.exploration_size < 1:
            raise ValueError("exploration_size must be at least one")
        if self.score_precision < 0:
            raise ValueError("score_precision cannot be negative")
        if self.house_sound_id is not None and self.house_sound_id <= 0:
            raise ValueError("house_sound_id must be positive or None")


@dataclass(frozen=True)
class CandidateScore:
    mix: Mix
    listener_scores: tuple[tuple[str, float], ...]
    mean: float
    minimum: float
    disagreement: float
    group_score: float

    def as_dict(self) -> dict:
        return {
            "mix_key": self.mix.key,
            "layers": self.mix.as_layers(),
            "listener_scores": {
                listener_key: score for listener_key, score in self.listener_scores
            },
            "mean": self.mean,
            "minimum": self.minimum,
            "disagreement": self.disagreement,
            "group_score": self.group_score,
        }


@dataclass(frozen=True)
class SelectionResult:
    selected_mix: Mix | None
    reason: str
    changed: bool
    explored: bool
    selected_action_probability: float
    candidate_count: int
    reachable_count: int
    action_probabilities: tuple[tuple[str, float], ...] = ()
    selected_score: CandidateScore | None = None
    ranked_scores: tuple[CandidateScore, ...] = ()

    def as_dict(self, *, top: int = 5) -> dict:
        return {
            "selected_mix_key": self.selected_mix.key if self.selected_mix else None,
            "selected_layers": (
                self.selected_mix.as_layers() if self.selected_mix else []
            ),
            "reason": self.reason,
            "changed": self.changed,
            "explored": self.explored,
            "selected_action_probability": self.selected_action_probability,
            "candidate_count": self.candidate_count,
            "reachable_count": self.reachable_count,
            "action_probabilities": dict(self.action_probabilities),
            "selected_score": self.selected_score.as_dict()
            if self.selected_score
            else None,
            "top_candidates": [score.as_dict() for score in self.ranked_scores[:top]],
        }


def enumerate_candidates(
    sounds: tuple[SoundEvidence, ...],
    *,
    min_layers: int = 1,
    max_layers: int = 3,
) -> tuple[Mix, ...]:
    if min_layers < 1:
        raise ValueError("min_layers must be at least one")
    if max_layers < 1:
        raise ValueError("max_layers must be at least one")
    if min_layers > max_layers:
        raise ValueError("min_layers cannot exceed max_layers")
    ordered_ids = sorted({sound.sound_id for sound in sounds})
    candidates: list[Mix] = []
    for count in range(min_layers, min(max_layers, len(ordered_ids)) + 1):
        gain = 1 / math.sqrt(count)
        for sound_ids in itertools.combinations(ordered_ids, count):
            candidates.append(
                Mix(
                    tuple(
                        MixLayer(sound_id=sound_id, gain=gain)
                        for sound_id in sound_ids
                    )
                )
            )
    return tuple(sorted(candidates, key=lambda mix: mix.key))


def _valid_current_mix(
    current_mix: Mix | None,
    available_ids: set[int],
    min_layers: int,
    max_layers: int,
) -> bool:
    return bool(
        current_mix
        and current_mix.layers
        and len(current_mix.layers) >= min_layers
        and len(current_mix.layers) <= max_layers
        and set(current_mix.sound_ids) <= available_ids
    )


def _is_reachable(current_mix: Mix | None, candidate: Mix) -> bool:
    if current_mix is None:
        return True
    current_ids = set(current_mix.sound_ids)
    candidate_ids = set(candidate.sound_ids)
    return max(
        len(candidate_ids - current_ids),
        len(current_ids - candidate_ids),
    ) <= 1


def _tag_profile(listener: ListenerEvidence) -> dict[str, float]:
    mass: dict[str, float] = {}
    contributing_sounds = 0
    for sound in listener.saved_sounds:
        if not sound.tags:
            continue
        contributing_sounds += 1
        contribution = 1 / len(sound.tags)
        for tag in sound.tags:
            mass[tag] = mass.get(tag, 0.0) + contribution
    if not contributing_sounds:
        return {}
    return {tag: value / contributing_sounds for tag, value in mass.items()}


def _listener_score(
    listener: ListenerEvidence,
    candidate: Mix,
    sounds_by_id: dict[int, SoundEvidence],
) -> float:
    profile = _tag_profile(listener)
    affinity = 0.0
    weight_total = 0.0
    for layer in candidate.layers:
        weight = layer.gain**2
        sound = sounds_by_id[layer.sound_id]
        sound_affinity = sum(profile.get(tag, 0.0) for tag in sound.tags)
        affinity += weight * sound_affinity
        weight_total += weight
    affinity = affinity / weight_total if profile and weight_total else 0.0
    prior = 0.5 + 0.25 * affinity

    votes = [vote for vote in listener.votes if vote.mix_key == candidate.key]
    positive_votes = sum(vote.positive for vote in votes)
    return (positive_votes + 2 * prior) / (len(votes) + 2)


def _score_candidate(
    candidate: Mix,
    listeners: tuple[ListenerEvidence, ...],
    sounds_by_id: dict[int, SoundEvidence],
    disagreement_penalty: float,
) -> CandidateScore:
    listener_scores = tuple(
        (listener.listener_key, _listener_score(listener, candidate, sounds_by_id))
        for listener in sorted(listeners, key=lambda item: item.listener_key)
    )
    values = [score for _, score in listener_scores]
    mean = statistics.fmean(values)
    disagreement = statistics.pstdev(values)
    return CandidateScore(
        mix=candidate,
        listener_scores=listener_scores,
        mean=mean,
        minimum=min(values),
        disagreement=disagreement,
        group_score=mean - disagreement_penalty * disagreement,
    )


def _neutral_candidate_score(candidate: Mix) -> CandidateScore:
    """Represent an unobserved candidate without inventing a listener."""
    return CandidateScore(
        mix=candidate,
        listener_scores=(),
        mean=0.5,
        minimum=0.5,
        disagreement=0.0,
        group_score=0.5,
    )


def _rank_scores(
    scores: list[CandidateScore],
    current_mix: Mix | None,
    precision: int,
    preferred_layer_count: int | None = None,
) -> tuple[CandidateScore, ...]:
    current_key = current_mix.key if current_mix else None
    return tuple(
        sorted(
            scores,
            key=lambda score: (
                -round(score.group_score, precision),
                -round(score.mean, precision),
                0 if score.mix.key == current_key else 1,
                (
                    abs(len(score.mix.layers) - preferred_layer_count)
                    if preferred_layer_count is not None
                    else 0
                ),
                len(score.mix.layers),
                score.mix.key,
            ),
        )
    )


def _fixed_result(
    selected_mix: Mix | None,
    reason: str,
    current_mix: Mix | None,
    candidate_count: int,
    *,
    reachable_count: int | None = None,
) -> SelectionResult:
    return SelectionResult(
        selected_mix=selected_mix,
        reason=reason,
        changed=(selected_mix.key if selected_mix else None)
        != (current_mix.key if current_mix else None),
        explored=False,
        selected_action_probability=1.0,
        candidate_count=candidate_count,
        reachable_count=(
            reachable_count
            if reachable_count is not None
            else (1 if selected_mix else 0)
        ),
        action_probabilities=((selected_mix.key, 1.0),) if selected_mix else (),
    )


def select_mix(
    *,
    sounds: tuple[SoundEvidence, ...],
    listeners: tuple[ListenerEvidence, ...],
    current_mix: Mix | None,
    last_change_at: datetime | None,
    decision_time: datetime,
    config: SelectionConfig = SelectionConfig(),
    rng: random.Random | None = None,
) -> SelectionResult:
    sounds = tuple(sorted(sounds, key=lambda sound: sound.sound_id))
    sound_ids = [sound.sound_id for sound in sounds]
    if len(sound_ids) != len(set(sound_ids)):
        raise ValueError("sounds must have unique sound IDs")
    listener_keys = [listener.listener_key for listener in listeners]
    if len(listener_keys) != len(set(listener_keys)):
        raise ValueError("listeners must have unique listener keys")
    sounds_by_id = {sound.sound_id: sound for sound in sounds}
    effective_min_layers = min(config.min_layers, len(sounds)) if sounds else 1
    candidates = list(
        enumerate_candidates(
            sounds,
            min_layers=effective_min_layers,
            max_layers=config.max_layers,
        )
    )
    candidate_count = len(candidates)
    available_ids = set(sounds_by_id)
    current_is_valid = _valid_current_mix(
        current_mix,
        available_ids,
        effective_min_layers,
        config.max_layers,
    )

    if not candidates:
        return _fixed_result(None, "no_feasible_mix", current_mix, 0)

    if current_is_valid and current_mix.key not in {mix.key for mix in candidates}:
        candidates.append(current_mix)

    maximum_stay_reached = False
    if current_is_valid and last_change_at is not None:
        elapsed = (decision_time - last_change_at).total_seconds()
        if elapsed < config.hold_seconds:
            return _fixed_result(
                current_mix,
                "minimum_hold",
                current_mix,
                candidate_count,
            )
        maximum_stay_reached = bool(
            config.maximum_stay_seconds is not None
            and elapsed >= config.maximum_stay_seconds
        )

    if not listeners and not maximum_stay_reached:
        if current_is_valid:
            return _fixed_result(
                current_mix,
                "retained_no_active_listeners",
                current_mix,
                candidate_count,
            )
        if config.house_sound_id in available_ids:
            house_mix = min(
                (
                    mix
                    for mix in candidates
                    if config.house_sound_id in mix.sound_ids
                ),
                key=lambda mix: (len(mix.layers), mix.key),
            )
            return _fixed_result(
                house_mix,
                "house_mix_no_active_listeners",
                current_mix,
                candidate_count,
            )
        return _fixed_result(
            None,
            "no_active_listener_fallback",
            current_mix,
            candidate_count,
        )

    reachable = [
        candidate
        for candidate in candidates
        if not current_is_valid or _is_reachable(current_mix, candidate)
    ]
    if maximum_stay_reached:
        reachable = [
            candidate
            for candidate in reachable
            if candidate.sound_ids != current_mix.sound_ids
        ]
        if not reachable:
            return _fixed_result(
                current_mix,
                "maximum_stay_unavailable",
                current_mix,
                candidate_count,
                reachable_count=0,
            )

    if listeners:
        scores = [
            _score_candidate(
                candidate,
                listeners,
                sounds_by_id,
                config.disagreement_penalty,
            )
            for candidate in reachable
        ]
    else:
        scores = [_neutral_candidate_score(candidate) for candidate in reachable]
    ranked = _rank_scores(
        scores,
        current_mix,
        config.score_precision,
        preferred_layer_count=(
            len(current_mix.layers) if maximum_stay_reached else None
        ),
    )
    winner = ranked[0]
    selected = winner
    explored = False
    selected_probability = 1.0
    action_probabilities = ((winner.mix.key, 1.0),)

    if config.exploration_probability > 0:
        generator = rng or random.Random()
        exploration_set = ranked[: config.exploration_size]
        explored = generator.random() < config.exploration_probability
        if explored:
            selected = generator.choice(exploration_set)
        selected_probability = (
            (1 - config.exploration_probability if selected is winner else 0)
            + config.exploration_probability / len(exploration_set)
        )
        action_probabilities = tuple(
            (
                score.mix.key,
                (
                    (1 - config.exploration_probability if score is winner else 0)
                    + config.exploration_probability / len(exploration_set)
                ),
            )
            for score in exploration_set
        )

    changed = not current_mix or selected.mix.key != current_mix.key
    if maximum_stay_reached:
        reason = "maximum_stay"
    elif explored:
        reason = "exploration"
    elif changed:
        reason = "selected"
    else:
        reason = "retained_best"
    return SelectionResult(
        selected_mix=selected.mix,
        reason=reason,
        changed=changed,
        explored=explored,
        selected_action_probability=selected_probability,
        candidate_count=candidate_count,
        reachable_count=len(reachable),
        action_probabilities=action_probabilities,
        selected_score=selected,
        ranked_scores=ranked,
    )
