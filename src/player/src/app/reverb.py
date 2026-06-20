"""A small feedback-delay-network (FDN) reverb with decorrelated returns.

This replaces the "dry, point-source" feel of the old player with the diffuse,
enveloping room the Max/Spat5 mixer had. The late field is what creates
envelopment *and* masks lossy-codec artefacts (see the design doc §4, §6).

Real-time constraints: an FDN's feedback is per-sample recursive, which is far
too slow as a Python loop in the audio callback. We avoid that by processing in
**chunks no longer than the shortest delay line** — within such a chunk every
delayed read comes from samples written in *previous* chunks, so the whole chunk
is computed with vectorised numpy (matrix mix + a one-zero damping filter). Only
the FIFO push is per-chunk. Pure numpy; no SciPy required.

Each of the N output channels taps the M delay lines through a different mixing
row, so the channels are mutually decorrelated — exactly what stops the reverb
from collapsing back to a point.
"""

import numpy as np

# Delay-line lengths in samples at 48 kHz (mutually coprime-ish for a dense,
# colourless tail). Scaled by sample rate and room size at construction.
_BASE_DELAYS = np.array([1297, 1559, 1871, 2243, 2693, 3187, 3719, 4297])


class FDNReverb:
    def __init__(
        self,
        channels: int,
        fs: int,
        room: float = 0.5,
        amount: float = 0.4,
        seed: int = 1234,
    ):
        self.channels = max(1, int(channels))
        self.fs = int(fs)
        self.m = len(_BASE_DELAYS)
        rng = np.random.default_rng(seed)

        # Delay lengths scale gently with room size and the actual sample rate.
        scale = (0.85 + 0.55 * float(np.clip(room, 0.0, 1.0))) * (self.fs / 48000.0)
        self.delays = np.maximum(257, (_BASE_DELAYS * scale).astype(int))
        self.min_delay = int(self.delays.min())

        # Lossless orthogonal feedback (Householder reflection) keeps the tail
        # dense without runaway gain; per-line attenuation sets the decay time.
        ones = np.ones((self.m, self.m), dtype=np.float64)
        self.matrix = (np.eye(self.m) - (2.0 / self.m) * ones).astype(np.float32)

        # Input fan-out and per-channel output mixing (random signs -> the N
        # returns are decorrelated from each other).
        self.b_in = (rng.choice([-1.0, 1.0], self.m) * 0.5).astype(np.float32)
        self.c_out = (
            rng.choice([-1.0, 1.0], size=(self.channels, self.m))
            / np.sqrt(self.m)
        ).astype(np.float32)

        # FIFO delay lines and the one-pole damping memory.
        self.z = [np.zeros(int(d), dtype=np.float32) for d in self.delays]
        self.damp_state = np.zeros(self.m, dtype=np.float32)
        self.damping = 0.35  # one-zero LP coefficient in the feedback path

        self.set_room(room)
        self.set_amount(amount)

    def set_room(self, room: float) -> None:
        """Map room size (0..1) onto a uniform RT60 across all delay lines."""
        room = float(np.clip(room, 0.0, 1.0))
        rt60 = 0.4 + 5.0 * room  # seconds
        # g_i so every line decays at the same rate regardless of its length.
        self.g = np.power(
            10.0, (-3.0 * self.delays) / (self.fs * rt60)
        ).astype(np.float32)

    def set_amount(self, amount: float) -> None:
        """Wet return level (0..1). Applied to the reverb output before mixing."""
        self.wet_gain = float(np.clip(amount, 0.0, 1.0))

    def reset(self) -> None:
        for buf in self.z:
            buf.fill(0.0)
        self.damp_state.fill(0.0)

    def process(self, send: np.ndarray) -> np.ndarray:
        """Render the mono ``send`` (shape ``(frames,)``) to ``(frames, N)`` wet."""
        send = np.ascontiguousarray(send, dtype=np.float32).reshape(-1)
        frames = send.shape[0]
        out = np.zeros((frames, self.channels), dtype=np.float32)
        if self.wet_gain <= 0.0 or frames == 0:
            # Still advance the delay lines so the tail stays time-consistent.
            self._advance(send, out, frames)
            return out
        self._advance(send, out, frames)
        out *= self.wet_gain
        return out

    def _advance(self, send: np.ndarray, out: np.ndarray, frames: int) -> None:
        pos = 0
        step = self.min_delay  # never read newer than one chunk ago
        while pos < frames:
            s = min(step, frames - pos)
            x = send[pos : pos + s]  # (s,)

            # Delayed outputs of every line for this chunk (all historical).
            tap = np.stack([self.z[i][:s] for i in range(self.m)])  # (M, s)

            # Decorrelated multichannel return taps the raw delayed signals.
            out[pos : pos + s, :] = (self.c_out @ tap).T  # (s, N)

            # Feedback: attenuate for decay, mix losslessly, damp the highs.
            mixed = self.matrix @ (self.g[:, None] * tap)  # (M, s)
            shifted = np.concatenate([self.damp_state[:, None], mixed[:, :-1]], axis=1)
            damped = (1.0 - self.damping) * mixed + self.damping * shifted
            self.damp_state = mixed[:, -1].copy()

            new = self.b_in[:, None] * x[None, :] + damped  # (M, s)
            for i in range(self.m):
                self.z[i] = np.concatenate([self.z[i][s:], new[i]])

            pos += s
