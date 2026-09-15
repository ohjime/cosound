from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN


MIX_KEY_PRECISION = Decimal("0.000001")


def _normalized_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({tag.strip().casefold() for tag in tags if tag.strip()}))


@dataclass(frozen=True, order=True)
class MixLayer:
    sound_id: int
    gain: float

    def __post_init__(self) -> None:
        if self.sound_id <= 0:
            raise ValueError("sound_id must be positive")
        if not math.isfinite(self.gain) or not 0 < self.gain <= 1:
            raise ValueError("gain must be finite and in (0, 1]")

    @property
    def serialized_gain(self) -> str:
        return format(
            Decimal(str(self.gain)).quantize(
                MIX_KEY_PRECISION,
                rounding=ROUND_HALF_EVEN,
            ),
            ".6f",
        )


@dataclass(frozen=True)
class Mix:
    layers: tuple[MixLayer, ...]

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.layers, key=lambda layer: layer.sound_id))
        if ordered != self.layers:
            object.__setattr__(self, "layers", ordered)
        ids = [layer.sound_id for layer in self.layers]
        if len(ids) != len(set(ids)):
            raise ValueError("a mix cannot contain the same sound more than once")

    @property
    def key(self) -> str:
        return "|".join(
            f"{layer.sound_id}@{layer.serialized_gain}" for layer in self.layers
        )

    @property
    def sound_ids(self) -> tuple[int, ...]:
        return tuple(layer.sound_id for layer in self.layers)

    def as_layers(self) -> list[dict[str, int | float]]:
        return [
            {"sound_id": layer.sound_id, "sound_gain": float(layer.serialized_gain)}
            for layer in self.layers
        ]


@dataclass(frozen=True)
class SoundEvidence:
    sound_id: int
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.sound_id <= 0:
            raise ValueError("sound_id must be positive")
        object.__setattr__(self, "tags", _normalized_tags(self.tags))


@dataclass(frozen=True)
class VoteEvidence:
    mix_key: str
    positive: bool

    def __post_init__(self) -> None:
        if not self.mix_key:
            raise ValueError("mix_key is required")
        if not isinstance(self.positive, bool):
            raise ValueError("positive must be a boolean")


@dataclass(frozen=True)
class ListenerEvidence:
    listener_key: str
    saved_sounds: tuple[SoundEvidence, ...] = ()
    votes: tuple[VoteEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not self.listener_key:
            raise ValueError("listener_key is required")
        saved_ids = [sound.sound_id for sound in self.saved_sounds]
        if len(saved_ids) != len(set(saved_ids)):
            raise ValueError("saved_sounds must have unique sound IDs")
