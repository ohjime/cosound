"""One layer of a saved mix as the server keeps it: a sound, a level, and how it
plays — the timing settings the card's gear edits, and SoundLayer's columns.

Everything that turns a posted layer into a stored one goes through here, so
the clamping, the rounding and what counts as "no timing at all" are decided in
one place. That last one matters most: a Cosound is found again by a hash of its
layers (Cosound.compute_hashid), and every mix saved before layers had timing
was hashed without any. A layer whose timing is the defaults — today's two
drifting copies, endlessly — therefore hashes exactly as it always did, and only
a layer that plays differently adds anything to the key.
"""

from dataclasses import dataclass, fields, replace
from decimal import ROUND_HALF_UP, ROUND_UP, Decimal, InvalidOperation


@dataclass(frozen=True)
class LayerSpec:
    sound_id: int
    gain: Decimal
    # Tape speed: pitch and schedule together.
    playback_rate: Decimal = Decimal("1.00")
    # Spacing: a pass repeats every length × stretch. 1 is back to back.
    stretch: Decimal = Decimal("1.75")
    # The second of the two offset copies, B.
    second_copy: bool = True
    # A cycle is `repetitions` periods followed by `cycle_rest` seconds of
    # silence; a rest of 0 is endless.
    repetitions: int = 1
    cycle_rest: Decimal = Decimal("0.0")
    # A wait before the layer's first pass.
    start_delay: Decimal = Decimal("0.0")
    # Phase shifting: B slips `phase_step` of a period later after
    # `phase_hold` passes, then after `phase_hold_alt` more, alternating.
    phase_step: Decimal = Decimal("0.000")
    phase_hold: int = 4
    phase_hold_alt: int = 4
    # The second copy's own tape speed, so the layer alternates between two
    # pitches. None plays B at `playback_rate`, as every layer did before.
    playback_rate_b: Decimal | None = None
    # Taking turns: B waits for A to finish, then `turn_gap` seconds, and A
    # waits the same after B, so the two pitches never sound over each other.
    # The gap is the spacing then, so `stretch` and the phase slip stand down.
    take_turns: bool = False
    turn_gap: Decimal = Decimal("0.0")

    @classmethod
    def from_post(cls, layer):
        """A layer as the save button posts it (soundscape-store saveLayers).

        Raises KeyError / TypeError / ValueError when there is no Sound id to
        point at — a blank layer, a local track — which parse_layers skips.
        Every timing value is optional: a missing or unreadable one is its
        default, and anything out of range is pulled back into it, so a
        tampered post can only ever ask for something the card could have.
        """
        sound_id = int(layer["sound_id"])
        gain = Decimal(str(max(0.0, min(1.0, float(layer.get("sound_gain", 1.0))))))
        timing = {name: _read(name, layer.get(name)) for name in TIMING_FIELDS}
        return cls(sound_id=sound_id, gain=gain, **timing)

    @classmethod
    def coerce(cls, layer):
        """A LayerSpec from whatever a caller holds.

        The vote path and older callers still pass `(sound_id, gain)` pairs,
        which are layers with the default timing; a bare id is a layer whose
        level does not matter (Cosound.with_sound_set).
        """
        if isinstance(layer, cls):
            return layer
        if isinstance(layer, (tuple, list)):
            sound_id, gain = layer
            return cls(sound_id=int(sound_id), gain=Decimal(str(gain)))
        return cls(sound_id=int(layer), gain=Decimal("0"))

    def normalized(self):
        """The same layer, rounded the way the hash needs it.

        The level is rounded up to the nearest 0.05 — the rounding every saved
        mix was hashed with — and settings that change nothing are put back to
        their defaults, so two layers that sound the same hash the same:
        repetitions without a rest, and phase shifting without a step or
        without a second copy to shift. The same goes for the second copy's
        settings without a second copy, a second rate equal to the first, a
        gap without turns — and, while the copies take turns, the spacing and
        the slip they ignore.
        """
        gain = (Decimal(str(self.gain)) * 2).quantize(Decimal("0.1"), rounding=ROUND_UP) / 2
        # Every value re-read through its limits, so a spec built by hand
        # (1.5) keys the same as one posted and stored (1.50).
        spec = replace(
            self,
            gain=gain,
            **{name: _read(name, value) for name, value in self.timing().items()},
        )
        if spec.cycle_rest == 0:
            spec = replace(spec, repetitions=DEFAULTS["repetitions"])
        if not spec.second_copy:
            spec = replace(spec, playback_rate_b=None, take_turns=False)
        if spec.playback_rate_b == spec.playback_rate:
            spec = replace(spec, playback_rate_b=None)
        if not spec.take_turns:
            spec = replace(spec, turn_gap=DEFAULTS["turn_gap"])
        else:
            spec = replace(spec, stretch=DEFAULTS["stretch"], phase_step=DEFAULTS["phase_step"])
        if spec.phase_step == 0 or not spec.second_copy:
            spec = replace(
                spec,
                phase_step=DEFAULTS["phase_step"],
                phase_hold=DEFAULTS["phase_hold"],
                phase_hold_alt=DEFAULTS["phase_hold_alt"],
            )
        return spec

    def timing(self):
        """The timing settings, by field name."""
        return {name: getattr(self, name) for name in TIMING_FIELDS}

    def timing_key(self):
        """What this layer's timing adds to the hash: nothing at the defaults."""
        if self.timing() == DEFAULTS:
            return ""
        key = (
            f"~r{self.playback_rate}s{self.stretch}c{int(self.second_copy)}"
            f"n{self.repetitions}w{self.cycle_rest}d{self.start_delay}"
            f"p{self.phase_step}h{self.phase_hold}k{self.phase_hold_alt}"
        )
        # Only when set, so every layer keyed before they existed keys the same.
        if self.playback_rate_b is not None:
            key += f"b{self.playback_rate_b}"
        if self.take_turns:
            key += f"t{self.turn_gap}"
        return key


TIMING_FIELDS = tuple(f.name for f in fields(LayerSpec) if f.name not in ("sound_id", "gain"))
DEFAULTS = {f.name: f.default for f in fields(LayerSpec) if f.name in TIMING_FIELDS}

# (lowest, highest, step, places) for the decimals; (lowest, highest) for the
# counts. The same ranges the card's sliders offer.
LIMITS = {
    "playback_rate": (Decimal("0.25"), Decimal("2.00"), Decimal("0.05"), Decimal("0.01")),
    "stretch": (Decimal("0.50"), Decimal("4.00"), Decimal("0.05"), Decimal("0.01")),
    "cycle_rest": (Decimal("0"), Decimal("300"), Decimal("0.5"), Decimal("0.1")),
    "start_delay": (Decimal("0"), Decimal("120"), Decimal("0.5"), Decimal("0.1")),
    "phase_step": (Decimal("0"), Decimal("0.5"), Decimal("0.005"), Decimal("0.001")),
    "playback_rate_b": (Decimal("0.25"), Decimal("2.00"), Decimal("0.05"), Decimal("0.01")),
    "turn_gap": (Decimal("0"), Decimal("60"), Decimal("0.1"), Decimal("0.1")),
    "repetitions": (1, 16),
    "phase_hold": (1, 64),
    "phase_hold_alt": (1, 64),
}


def _read(name, raw):
    """One posted timing value, defaulted, clamped and snapped to its step."""
    default = DEFAULTS[name]
    if name == "playback_rate_b" and (raw is None or raw == ""):
        return None
    if name in ("second_copy", "take_turns"):
        if raw is None:
            return default
        if isinstance(raw, str):
            return raw.strip().lower() not in ("", "0", "false", "no", "off")
        return bool(raw)
    limits = LIMITS[name]
    if len(limits) == 2:
        low, high = limits
        try:
            return max(low, min(high, int(round(float(raw)))))
        except (TypeError, ValueError, OverflowError):
            return default
    low, high, step, places = limits
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return default
    if raw is None or not value.is_finite():
        return default
    value = max(low, min(high, value))
    steps = (value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return (steps * step).quantize(places)
