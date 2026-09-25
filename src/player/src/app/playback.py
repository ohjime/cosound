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


# Catch-up after a dropout or clock step: resampling moves pitch with speed,
# and 0.5% is ~9 cents, too little to hear in a sustained tone. Reaching it
# over a quarter second glides instead of stepping. With the half-second
# proportional term, the correction never has to fall faster than the glide
# allows, so it settles without overshooting.
MAX_CORRECTION = 0.005
CORRECTION_SECONDS = 0.5
CORRECTION_SLEW_SECONDS = 0.25
# Beyond this, catching up would take most of a minute. Jump, but fade the
# old position out over 50 ms: a 5 ms blend between unrelated points in a
# loop still clicks.
SEEK_SECONDS = 0.25
SEEK_FADE_SECONDS = 0.05


def loop_chunk(track, frames, server_time, epoch, sample_rate):
    """Read fractional samples and gently chase the shared DAC-time phase.

    Canonical duration is captured BEFORE device-rate resampling. Rounding a
    loop to a device's sample count must never accumulate a phase error on
    every repeat. Errors up to SEEK_SECONDS, including every skipped device
    cycle, are recovered by a small speed change that glides in and out.
    Larger ones (a reconnect, waking from sleep) jump with a crossfade.
    """
    data = track["data"]
    length = len(data)
    duration = track["duration"]
    base_rate = length / (duration * sample_rate)
    desired = ((server_time - epoch) % duration) * length / duration
    pointer = track.get("sync_ptr", desired)
    error = (desired - pointer + length / 2) % length - length / 2
    error_seconds = error * duration / length
    track["sync_error_ms"] = error_seconds * 1000
    correction = track.get("sync_correction", 0.0)
    if abs(error_seconds) > SEEK_SECONDS:
        track["fade_ptr"], track["fade_done"] = pointer, 0
        pointer, correction = desired, 0.0
    else:
        wanted = np.clip(error_seconds / CORRECTION_SECONDS, -MAX_CORRECTION, MAX_CORRECTION)
        step = MAX_CORRECTION * frames / (sample_rate * CORRECTION_SLEW_SECONDS)
        correction += float(np.clip(wanted - correction, -step, step))
    rate = base_rate * (1 + correction)

    def read(start, speed):
        positions = (start + np.arange(frames) * speed) % length
        indices = positions.astype(np.int64)
        fraction = (positions - indices).astype(np.float32)[:, None]
        return data[indices] * (1 - fraction) + data[(indices + 1) % length] * fraction

    chunk = read(pointer, rate)
    if "fade_ptr" in track:
        # Equal power: the two positions are unrelated material, so a linear
        # fade would dip in the middle.
        fade_frames = max(1, round(sample_rate * SEEK_FADE_SECONDS))
        done = track["fade_done"]
        progress = np.minimum((done + np.arange(frames)) / fade_frames, 1)[:, None] * (np.pi / 2)
        chunk = read(track["fade_ptr"], base_rate) * np.cos(progress) + chunk * np.sin(progress)
        if done + frames >= fade_frames:
            del track["fade_ptr"], track["fade_done"]
        else:
            track["fade_ptr"] = (track["fade_ptr"] + frames * base_rate) % length
            track["fade_done"] = done + frames
    track["sync_ptr"] = (pointer + frames * rate) % length
    track["sync_correction"] = correction
    return chunk.astype(np.float32)
