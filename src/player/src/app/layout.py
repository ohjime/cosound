"""Speaker-layout inference and render-mode selection.

Given only a channel count (and best-effort sub hints) from :mod:`devices`, this
infers a plausible speaker geometry and decides how to render:

* a recognised standard layout (2/4/6/8) → ``vbap`` with real angles;
* anything unusual, or where we are not confident → ``upmix`` (geometry-free
  decorrelation that envelops on any channel count).

Azimuth convention: degrees, ``0`` = front-centre, positive = clockwise (to the
listener's right). True physical angles are not knowable from the audio stack, so
these are conventions, overridable via config. See the design doc §7.
"""

from dataclasses import dataclass, field

from app.devices import OutputDevice


def wrap180(deg: float) -> float:
    """Wrap an angle to the [-180, 180) range."""
    return (deg + 180.0) % 360.0 - 180.0


def even_ring(n: int) -> list[float]:
    """``n`` azimuths spaced evenly around the listener, starting at front."""
    return [wrap180(i * 360.0 / n) for i in range(n)]


# Standard interleaved layouts: channel-index → azimuth, plus LFE indices.
# (Only the common cases; everything else falls back to an even ring / upmix.)
_STANDARD = {
    4: {"az": {0: -45.0, 1: 45.0, 2: -135.0, 3: 135.0}, "lfe": []},
    6: {"az": {0: -30.0, 1: 30.0, 2: 0.0, 4: -110.0, 5: 110.0}, "lfe": [3]},
}


@dataclass
class SpeakerLayout:
    """Resolved output geometry and the render mode chosen for it."""

    channels: int  # total output channels
    mode: str  # "vbap" | "upmix"
    confidence: str  # "high" | "medium" | "low"
    # Positional speakers, in ring order: output channel index -> azimuth (deg).
    positional: list[int] = field(default_factory=list)
    azimuths: list[float] = field(default_factory=list)
    lfe_channels: list[int] = field(default_factory=list)

    def describe(self) -> str:
        if self.mode == "upmix":
            return f"{self.channels}ch decorrelated upmix ({self.confidence})"
        if self.mode == "stereo":
            return f"{self.channels}ch stereo pan ({self.confidence})"
        ring = ", ".join(f"{a:+.0f}°" for a in self.azimuths)
        subs = f" +{len(self.lfe_channels)} sub" if self.lfe_channels else ""
        return f"{self.channels}ch VBAP [{ring}]{subs} ({self.confidence})"


def _van_der_corput(i: int, base: int = 2) -> float:
    """Low-discrepancy fraction in [0, 1); successive values spread out evenly."""
    f, r = 1.0, 0.0
    while i > 0:
        f /= base
        r += f * (i % base)
        i //= base
    return r


def default_source_azimuths(n: int) -> list[float]:
    """Default positions for ``n`` layered sources, spread around the listener.

    Ordered by a van der Corput sequence so that *any prefix* stays balanced
    around the circle — with 4 active layers you get roughly front/back/right/
    left, not four sources piled onto one side.
    """
    return [wrap180(_van_der_corput(i) * 360.0) for i in range(max(0, n))]


def infer_layout(device: OutputDevice, override: dict | None = None) -> SpeakerLayout:
    """Infer a :class:`SpeakerLayout` for ``device``.

    ``override`` (typically from config) may set any of: ``mode`` ("vbap"/
    "upmix"), ``azimuths`` (list, one per positional channel), ``lfe_channels``
    (list of indices). Provided keys win; the rest are inferred.
    """
    override = override or {}
    n = int(device.channels)

    forced_mode = override.get("mode")
    lfe = list(override.get("lfe_channels", device.lfe_channels))

    # Explicit azimuths from config -> trust them, use VBAP.
    if override.get("azimuths"):
        az = [float(a) for a in override["azimuths"]]
        positional = [c for c in range(n) if c not in lfe][: len(az)]
        return SpeakerLayout(n, forced_mode or "vbap", "high", positional, az, lfe)

    if n <= 1:
        # A single output: nothing to position. Upmix routes everything to it.
        return SpeakerLayout(n, forced_mode or "upmix", "high", [0], [0.0], [])

    if n == 2:
        # Two channels (incl. headphones / AirPods). A ±30° VBAP pair places
        # sound in a narrow frontal arc and snaps everything else onto the nearer
        # side (layered scenes leaned hard right). Decorrelated upmix balances it
        # but its per-ear random-phase all-pass smears transients on headphones
        # (sounds "lossy"). Constant-power stereo panning is clean *and* balanced;
        # binaural HRTF is the future upgrade.
        return SpeakerLayout(n, forced_mode or "stereo", "high", [0, 1], [-30.0, 30.0], lfe)

    if n in _STANDARD:
        spec = _STANDARD[n]
        lfe = lfe or list(spec["lfe"])
        positional = sorted(spec["az"].keys())
        az = [spec["az"][c] for c in positional]
        return SpeakerLayout(n, forced_mode or "vbap", "high", positional, az, lfe)

    if n == 8:
        # Ambiguous: could be 7.1 or a bare 8-ring. The AAS soundscape use case
        # is an even ring, which is also more robust for diffuse material.
        positional = list(range(8))
        return SpeakerLayout(n, forced_mode or "vbap", "medium", positional, even_ring(8), lfe)

    # Unusual channel count: we can still describe an even ring, but we are not
    # confident it matches reality -> default to the geometry-free upmix.
    positional = [c for c in range(n) if c not in lfe]
    az = even_ring(len(positional))
    return SpeakerLayout(n, forced_mode or "upmix", "low", positional, az, lfe)
