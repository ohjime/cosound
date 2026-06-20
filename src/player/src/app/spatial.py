"""Spatial renderers: positional VBAP and a geometry-free decorrelated upmix.

Both replace the old ``_adapt_channels_for_output``, which copied the *same*
(correlated) signal to many speakers — the thing that made sources collapse to
the nearest speaker and comb-filter into "noise" (design doc §4).

* :class:`VBAPRenderer` pans each source to a point between the two nearest
  speakers of a known ring, optionally rotating the field, and sends a
  low-passed sum to any sub channels.
* :class:`DecorrelatedUpmixRenderer` spreads sound across *any* channel count by
  giving each speaker a phase-decorrelated copy (flat magnitude, scrambled
  phase), so neighbours are no longer identical — enveloping without geometry.

Each renderer returns the dry multichannel output plus a mono reverb send.
"""

from abc import ABC, abstractmethod

import numpy as np

from app.layout import SpeakerLayout


def _downmix_mono(signal: np.ndarray) -> np.ndarray:
    """(frames, ch) or (frames,) -> (frames,) average."""
    if signal.ndim == 1:
        return signal
    if signal.shape[1] == 1:
        return signal[:, 0]
    return signal.mean(axis=1)


def _az_vector(az_deg: float) -> np.ndarray:
    """Azimuth (deg, 0=front, +=right) -> unit vector [x=right, y=front]."""
    r = np.radians(az_deg)
    return np.array([np.sin(r), np.cos(r)], dtype=np.float64)


def make_decorrelation_fir(n_taps: int, seed: int) -> np.ndarray:
    """A flat-magnitude, random-phase all-pass kernel (energy-normalised).

    Flat magnitude means it decorrelates without colouring the spectrum (no comb
    filtering), unlike copying or plain delays. A different ``seed`` per channel
    yields mutually decorrelated copies.
    """
    rng = np.random.default_rng(seed)
    bins = n_taps // 2 + 1
    phase = rng.uniform(-np.pi, np.pi, bins)
    phase[0] = 0.0  # DC real
    if n_taps % 2 == 0:
        phase[-1] = 0.0  # Nyquist real
    spectrum = np.exp(1j * phase)
    h = np.fft.irfft(spectrum, n_taps)
    # Taper the edges so the impulse is reasonably compact in time.
    h *= np.hanning(n_taps)
    norm = np.sqrt(np.sum(h * h)) or 1.0
    return (h / norm).astype(np.float32)


def make_lowpass_fir(cutoff_hz: float, fs: int, n_taps: int = 257) -> np.ndarray:
    """Linear-phase windowed-sinc low-pass (for the sub/LFE crossover)."""
    if n_taps % 2 == 0:
        n_taps += 1
    fc = float(cutoff_hz) / (fs * 0.5)  # normalised to Nyquist
    n = np.arange(n_taps) - (n_taps - 1) / 2.0
    sinc = np.sinc(fc * n) * fc
    h = sinc * np.hamming(n_taps)
    h /= np.sum(h) or 1.0
    return h.astype(np.float32)


class StreamFIR:
    """Stateful linear convolution for block streaming (overlap-save)."""

    def __init__(self, h: np.ndarray):
        self.h = np.ascontiguousarray(h, dtype=np.float32)
        self.n = len(self.h)
        self.tail = np.zeros(max(0, self.n - 1), dtype=np.float32)

    def process(self, x: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(x, dtype=np.float32).reshape(-1)
        if self.n <= 1:
            return x * self.h[0] if self.n == 1 else x
        buf = np.concatenate([self.tail, x])
        full = np.convolve(buf, self.h)
        y = full[self.n - 1 : self.n - 1 + len(x)]
        self.tail = buf[-(self.n - 1) :]
        return y.astype(np.float32)


class SpatialRenderer(ABC):
    """Renders a list of positioned sources to the output channel layout."""

    def __init__(self, layout: SpeakerLayout, fs: int):
        self.layout = layout
        self.channels = layout.channels
        self.fs = int(fs)

    @abstractmethod
    def render(self, sources: list[dict], frames: int) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(out (frames, channels), send (frames,))``.

        ``sources`` items: ``{"signal": (frames, src_ch) float32, "azimuth":
        float | None}``. ``signal`` already has its per-track gain applied.
        """


class VBAPRenderer(SpatialRenderer):
    """Pairwise 2-D vector-base amplitude panning over a known speaker ring."""

    def __init__(
        self,
        layout: SpeakerLayout,
        fs: int,
        sub_crossover_hz: float = 110.0,
        rotation_deg_per_s: float = 0.0,
    ):
        super().__init__(layout, fs)
        self.rotation_deg_per_s = float(rotation_deg_per_s)
        self._angle = 0.0

        # Speaker ring: output-channel index + unit vector, sorted by azimuth.
        ring = sorted(zip(layout.positional, layout.azimuths), key=lambda p: p[1])
        self._chan = [c for c, _ in ring]
        self._vecs = [_az_vector(a) for _, a in ring]

        # Precompute the inverse base matrix for every adjacent speaker arc
        # (including the wrap-around arc) for fast VBAP gain solving.
        self._arcs = []
        k = len(self._chan)
        for i in range(k if k > 2 else max(0, k - 1)):
            ia, ib = i, (i + 1) % k
            if ia == ib:
                continue
            base = np.column_stack([self._vecs[ia], self._vecs[ib]])
            try:
                inv = np.linalg.inv(base)
            except np.linalg.LinAlgError:
                continue
            self._arcs.append((ia, ib, inv))

        self.lfe = list(layout.lfe_channels)
        self._sub_fir = (
            StreamFIR(make_lowpass_fir(sub_crossover_hz, fs)) if self.lfe else None
        )

    def _pan_gains(self, az_deg: float) -> tuple[int, int, float, float]:
        """Channel indices + gains for a source at ``az_deg`` (energy-normalised)."""
        if len(self._chan) == 1:
            return self._chan[0], self._chan[0], 1.0, 0.0
        p = _az_vector(az_deg)
        best = None
        for ia, ib, inv in self._arcs:
            g = inv @ p
            if g[0] >= -1e-6 and g[1] >= -1e-6:
                best = (ia, ib, g)
                break
        if best is None:
            # Outside every arc (e.g. a partial ring): snap to nearest speaker.
            dots = [float(np.dot(p, v)) for v in self._vecs]
            i = int(np.argmax(dots))
            return self._chan[i], self._chan[i], 1.0, 0.0
        ia, ib, g = best
        g = np.clip(g, 0.0, None)
        norm = np.sqrt(float(g[0] ** 2 + g[1] ** 2)) or 1.0
        g = g / norm
        return self._chan[ia], self._chan[ib], float(g[0]), float(g[1])

    def render(self, sources, frames):
        out = np.zeros((frames, self.channels), dtype=np.float32)
        send = np.zeros(frames, dtype=np.float32)
        sub = np.zeros(frames, dtype=np.float32) if self._sub_fir is not None else None

        for src in sources:
            mono = _downmix_mono(src["signal"])
            send += mono
            if sub is not None:
                sub += mono
            az = src.get("azimuth")
            az = (0.0 if az is None else float(az)) + self._angle
            c1, c2, g1, g2 = self._pan_gains(az)
            out[:, c1] += mono * g1
            if c2 != c1:
                out[:, c2] += mono * g2

        if sub is not None:
            low = self._sub_fir.process(sub)
            for ch in self.lfe:
                out[:, ch] += low

        # Advance the field rotation for next block.
        if self.rotation_deg_per_s:
            self._angle = (self._angle + self.rotation_deg_per_s * frames / self.fs) % 360.0
        return out, send


class DecorrelatedUpmixRenderer(SpatialRenderer):
    """Spread sound across any channel count via per-channel phase decorrelation."""

    def __init__(self, layout: SpeakerLayout, fs: int, n_taps: int = 512, seed: int = 7):
        super().__init__(layout, fs)
        self._fir = [
            StreamFIR(make_decorrelation_fir(n_taps, seed + 101 * ch))
            for ch in range(self.channels)
        ]
        # Keep per-channel acoustic power ~constant as channel count grows.
        self._gain = float(np.sqrt(2.0 / max(1, self.channels)))

    def render(self, sources, frames):
        out = np.zeros((frames, self.channels), dtype=np.float32)
        send = np.zeros(frames, dtype=np.float32)
        if not sources:
            return out, send

        # Sum sources into a stereo bus (mono sources feed both sides equally).
        left = np.zeros(frames, dtype=np.float32)
        right = np.zeros(frames, dtype=np.float32)
        for src in sources:
            sig = src["signal"]
            if sig.ndim == 1 or sig.shape[1] == 1:
                m = _downmix_mono(sig)
                left += m
                right += m
            else:
                left += sig[:, 0]
                right += sig[:, 1]
        send = 0.5 * (left + right)

        if self.channels == 1:
            out[:, 0] = send
            return out, send

        for ch in range(self.channels):
            base = left if ch % 2 == 0 else right
            out[:, ch] = self._fir[ch].process(base) * self._gain
        return out, send


class StereoPanRenderer(SpatialRenderer):
    """Clean constant-power amplitude panning for a 2-channel / headphone output.

    Headphones expose the listener directly to interaural phase, so the
    decorrelation upmix (a different random-phase all-pass per ear) smears
    transients and destabilises the phantom centre — it sounds washed-out and
    "lossy". A frontal VBAP pair, conversely, snaps everything onto the nearer
    side. Plain constant-power panning by source azimuth does neither: it is
    phase-coherent (no filtering whatsoever), balanced, and still gives real L/R
    width. True binaural HRTF (front/back + elevation) is the future upgrade.
    """

    def render(self, sources, frames):
        out = np.zeros((frames, self.channels), dtype=np.float32)
        send = np.zeros(frames, dtype=np.float32)

        for src in sources:
            sig = src["signal"]
            az = src.get("azimuth")
            # Azimuth (0=front, +=right) -> lateral position; front and back both
            # fold to centre in plain stereo (that distinction needs binaural).
            x = float(np.sin(np.radians(0.0 if az is None else float(az))))
            theta = (np.clip(x, -1.0, 1.0) * 0.5 + 0.5) * (np.pi / 2.0)
            gl, gr = float(np.cos(theta)), float(np.sin(theta))  # constant power

            if sig.ndim == 1 or sig.shape[1] == 1:
                mono = _downmix_mono(sig)
                out[:, 0] += mono * gl
                out[:, 1] += mono * gr
                send += mono
            else:
                # Already-stereo content keeps its own image; don't re-pan it.
                out[:, 0] += sig[:, 0]
                out[:, 1] += sig[:, 1]
                send += 0.5 * (sig[:, 0] + sig[:, 1])

        return out, send


def make_renderer(layout: SpeakerLayout, fs: int, **kwargs) -> SpatialRenderer:
    """Construct the renderer the layout asked for."""
    if layout.mode == "vbap":
        return VBAPRenderer(
            layout,
            fs,
            sub_crossover_hz=kwargs.get("sub_crossover_hz", 110.0),
            rotation_deg_per_s=kwargs.get("rotation_deg_per_s", 0.0),
        )
    if layout.mode == "stereo":
        return StereoPanRenderer(layout, fs)
    return DecorrelatedUpmixRenderer(layout, fs)
