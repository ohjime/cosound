"""Shared loop phase and gain envelopes, independent of network arrival time."""

from dataclasses import dataclass
import math

import numpy as np


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Playback timing must contain finite numbers")
    return float(value)


@dataclass(frozen=True)
class PlaybackPlan:
    revision: str
    epoch: float
    effective_at: float
    fade_seconds: float
    previous: dict
    target: dict

    @classmethod
    def parse(cls, descriptor, layers):
        if not isinstance(descriptor, dict) or descriptor.get("version") != 1:
            raise ValueError("Unsupported playback timeline")
        revision = descriptor.get("revision")
        if not isinstance(revision, str) or not revision:
            raise ValueError("Playback revision is required")
        epoch = _number(descriptor.get("epoch"))
        effective_at = _number(descriptor.get("effective_at"))
        fade = _number(descriptor.get("fade_seconds"))
        if epoch <= 0 or effective_at < epoch or not 0 <= fade <= 60:
            raise ValueError("Invalid playback timeline")

        def gains(items):
            if not isinstance(items, list):
                raise ValueError("Invalid playback layers")
            result = {}
            for item in items:
                sound_id = item.get("sound_id")
                gain = _number(item.get("gain"))
                if type(sound_id) is not int or sound_id <= 0 or not 0 <= gain <= 1:
                    raise ValueError("Invalid playback layer")
                result[str(sound_id)] = gain
            return result

        return cls(revision, epoch, effective_at, fade,
                   gains(descriptor.get("previous_layers", [])), gains(layers))

    def gains(self, sound_id, times):
        start = self.previous.get(sound_id, 0.0)
        target = self.target.get(sound_id, 0.0)
        progress = (np.clip((times - self.effective_at) / self.fade_seconds, 0, 1)
                    if self.fade_seconds else np.ones(len(times)))
        return start + (target - start) * progress


def loop_chunk(track, frames, server_time, epoch, sample_rate):
    """Read fractional samples and gently chase the shared DAC-time phase.

    Canonical duration is captured BEFORE device-rate resampling. Rounding a
    loop to a device's sample count must never accumulate a phase error on
    every repeat. Small clock errors slew over 0.5 s, capped at 0.2%; a dropout
    or clock step over 20 ms rejoins immediately with a short de-click blend.
    """
    data = track["data"]
    length = len(data)
    duration = track["duration"]
    base_rate = length / (duration * sample_rate)
    desired = ((server_time - epoch) % duration) * length / duration
    pointer = track.get("sync_ptr", desired)
    error = (desired - pointer + length / 2) % length - length / 2
    track["sync_error_ms"] = error * duration / length * 1000
    seek = abs(error) * duration / length > 0.020
    rate = base_rate + np.clip(error / (0.5 * sample_rate),
                              -0.002 * base_rate, 0.002 * base_rate)
    if seek:
        pointer, rate = desired, base_rate

    def read(start, speed):
        positions = (start + np.arange(frames) * speed) % length
        indices = positions.astype(np.int64)
        fraction = (positions - indices).astype(np.float32)[:, None]
        return data[indices] * (1 - fraction) + data[(indices + 1) % length] * fraction

    chunk = read(pointer, rate)
    if seek:
        old = read(track["sync_ptr"], base_rate)
        blend = np.minimum(np.arange(frames) / max(1, sample_rate * 0.005), 1)
        chunk = old * (1 - blend[:, None]) + chunk * blend[:, None]
    track["sync_ptr"] = (pointer + frames * rate) % length
    return chunk.astype(np.float32)
