"""Microphone-driven master gain: raises the player as the room gets louder.

On start we briefly listen to the room to calibrate a quiet-room baseline
(dBFS). From then on, the player's *ceiling* gain (``max_gain``, set by the
volume slider) only ever gets scaled **up** as the live mic level rises
above that baseline — never down. At or below the baseline the player plays
at a quiet floor (``min_scale`` of ``max_gain``); ``max_gain`` itself is only
reached once the room is ``attenuation_range_db`` louder than baseline. This
is a "talk louder to hear it louder" behaviour: sound the mic picks up
(voices, ambient noise) pushes the volume up, so the slider sets a true
ceiling that's only reached in a loud room.

To stay smooth rather than twitchy, the gain factor isn't driven by the
instantaneous mic level — it's driven by a rolling average of mic *energy*
over the last ``window_seconds`` (default 60s). That's the piece that makes
this "sustained" in the right sense: an ordinary conversation has pauses
between words and sentences, so requiring the level to stay elevated with no
gaps would never trigger on real speech. Averaging energy over the window
instead means a conversation that keeps going for the length of the window
raises the average and raises the volume, while a single short blip (a door
slam, one comment) barely moves a 60-second average.

On top of that, the applied gain is slew-rate-limited so a full 0→1 swing
takes about ``ramp_seconds`` (default 60s) — the volume glides rather than
jumps.
"""

import threading
import time
import math
from collections import deque

import numpy as np
import sounddevice as sd

from app.devices import detect_input

# How long to listen before locking in the quiet-room baseline.
CALIBRATION_SECONDS = 1.5
# Rolling window of mic energy the gain factor is computed from. This is
# what makes conversations-with-pauses register as "sustained".
WINDOW_SECONDS = 60.0
# dB above baseline (measured over the rolling window) needed to reach full
# gain (scale 1.0, i.e. max_gain).
ATTENUATION_RANGE_DB = 15.0
# Scale at/below baseline — the quiet-room floor, as a fraction of max_gain
# (avoids hard mute).
MIN_SCALE = 0.1
# How long the audible gain takes to glide across the full 0..1 range.
RAMP_SECONDS = 60.0
# Exponential smoothing applied to the raw dBFS reading during calibration
# only — just enough to denoise a single block.
CALIBRATION_SMOOTHING = 0.25


def _block_energy(block: np.ndarray) -> float:
    """Mean squared amplitude (linear power) of a block."""
    return float(np.mean(np.square(block))) if block.size else 0.0


def _rms_dbfs(block: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0
    if rms <= 1e-9:
        return -120.0
    return 20.0 * math.log10(rms)


class MicGainController:
    """Calibrates a mic baseline, then slowly raises the player's gain as noise rises."""

    def __init__(
        self,
        player,
        device=None,
        max_gain: float = 0.05,
        blocksize: int = 2048,
        calibration_seconds: float = CALIBRATION_SECONDS,
        window_seconds: float = WINDOW_SECONDS,
        attenuation_range_db: float = ATTENUATION_RANGE_DB,
        min_scale: float = MIN_SCALE,
        ramp_seconds: float = RAMP_SECONDS,
        calibration_smoothing: float = CALIBRATION_SMOOTHING,
    ):
        self.player = player
        self.device_obj = detect_input(device)
        self.calibration_seconds = float(calibration_seconds)
        self.window_seconds = float(window_seconds)
        self.attenuation_range_db = float(attenuation_range_db)
        self.min_scale = max(0.0, min(1.0, float(min_scale)))
        self.ramp_seconds = float(ramp_seconds)
        self.calibration_smoothing = float(calibration_smoothing)

        self.lock = threading.Lock()
        self._max_gain = max(0.0, min(1.0, float(max_gain)))
        self._level_db = None  # smoothed running dBFS, calibration phase only
        self._baseline_db = None  # locked in once calibration completes
        self._calibration_frames = 0
        self._calibration_target_frames = 0

        # Rolling (timestamp, energy, duration) samples covering the last
        # `window_seconds` — the basis for the duck decision.
        self._window: deque[tuple[float, float, float]] = deque()
        self._window_energy_duration = 0.0  # sum(energy * duration) in the window
        self._window_duration = 0.0  # sum(duration) in the window

        self._scale = 1.0
        self._last_callback_time = None

        self.stream = None

        if self.device_obj is None:
            return

        self._calibration_target_frames = int(
            self.device_obj.samplerate * self.calibration_seconds
        )

        self.stream = sd.InputStream(
            samplerate=self.device_obj.samplerate,
            channels=1,
            device=self.device_obj.index,
            callback=self._audio_callback,
            blocksize=blocksize,
            dtype="float32",
        )

    @property
    def available(self) -> bool:
        return self.stream is not None

    @property
    def calibrated(self) -> bool:
        with self.lock:
            return self._baseline_db is not None

    def start(self) -> None:
        if self.stream is not None:
            self.stream.start()

    def stop(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()

    def set_max_gain(self, value: float) -> None:
        """Set the ceiling (from the volume slider); mic scaling applies below it."""
        with self.lock:
            self._max_gain = max(0.0, min(1.0, float(value)))
            scale = self._scale
        self.player.set_master_gain(self._max_gain * scale)

    def get_max_gain(self) -> float:
        with self.lock:
            return self._max_gain

    def get_scale(self) -> float:
        """Latest applied gain factor in [min_scale, 1.0]; 1.0 == at the ceiling."""
        with self.lock:
            return self._scale

    def get_baseline_db(self) -> float | None:
        with self.lock:
            return self._baseline_db

    def _push_window_sample(self, now: float, energy: float, duration: float) -> None:
        self._window.append((now, energy, duration))
        self._window_energy_duration += energy * duration
        self._window_duration += duration
        cutoff = now - self.window_seconds
        while self._window and self._window[0][0] < cutoff:
            _, old_energy, old_duration = self._window.popleft()
            self._window_energy_duration -= old_energy * old_duration
            self._window_duration -= old_duration

    def _window_avg_db(self) -> float:
        if self._window_duration <= 0:
            return -120.0
        avg_energy = self._window_energy_duration / self._window_duration
        if avg_energy <= 1e-18:
            return -120.0
        return 10.0 * math.log10(avg_energy)

    def _desired_scale(self) -> float:
        avg_db = self._window_avg_db()
        excess_db = max(0.0, avg_db - self._baseline_db)
        factor = self.min_scale + (excess_db / self.attenuation_range_db) * (
            1.0 - self.min_scale
        )
        return max(self.min_scale, min(1.0, factor))

    def _audio_callback(self, indata, frames, time_info, status):
        now = time.monotonic()
        energy = _block_energy(indata)

        with self.lock:
            if self._baseline_db is None:
                # Calibration window: track the room's quiet level, play at
                # the quiet floor (min_scale) until the baseline locks in.
                db = _rms_dbfs(indata)
                if self._level_db is None:
                    self._level_db = db
                else:
                    self._level_db = (
                        self.calibration_smoothing * db
                        + (1 - self.calibration_smoothing) * self._level_db
                    )
                self._calibration_frames += frames
                if self._calibration_frames >= self._calibration_target_frames:
                    self._baseline_db = self._level_db
                self._scale = self.min_scale
                self._last_callback_time = now
            else:
                duration = frames / float(self.device_obj.samplerate)
                self._push_window_sample(now, energy, duration)
                desired = self._desired_scale()

                # Slew-limit toward the desired scale so a full 0..1 swing
                # takes about `ramp_seconds`, regardless of callback rate.
                dt = now - self._last_callback_time if self._last_callback_time else 0.0
                self._last_callback_time = now
                max_step = dt / self.ramp_seconds if self.ramp_seconds > 0 else 1.0
                delta = max(-max_step, min(max_step, desired - self._scale))
                self._scale += delta

            max_gain = self._max_gain
            scale = self._scale

        self.player.set_master_gain(max_gain * scale)
