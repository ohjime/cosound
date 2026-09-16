"""Output device probing and auto-detection.

The audio stack (PortAudio via sounddevice) only tells us three reliable things
about an output: its **channel count**, its **default sample rate**, and its
**name**. It does *not* expose physical speaker angles, and it does not expose
per-channel labels (CoreAudio has them, but PortAudio drops them). So this module
gathers exactly what is knowable and leaves the geometry inference to ``layout``.

See ``docs/player-audio-fidelity-and-spatialization.md`` §7 for the rationale.
"""

from dataclasses import dataclass, field

import sounddevice as sd


# The ALSA/PulseAudio *plugin* devices ("default", "pipewire", "pulse",
# "Default Sink") advertise a routing **maximum**, not a speaker count: they
# accept any layout and remap it, so PortAudio reports 128 (ALSA) or 32 (Pulse).
# Taking those literally sends `layout.infer_layout` down the unusual-count path
# — a decorrelated upmix at sqrt(2/N) gain — while the sink still only plays
# channels 0 and 1, so most of the signal is attenuated and then discarded.
# Above this many channels we treat the count as unknown rather than real.
MAX_PLAUSIBLE_CHANNELS = 8
ASSUMED_CHANNELS = 2


@dataclass
class OutputDevice:
    """What we can reliably learn about a selected output device."""

    index: int | None  # None == system default output
    name: str
    channels: int  # max_output_channels, sentinel counts resolved
    samplerate: int  # device default sample rate
    hostapi: str
    # Best-effort: indices we believe are sub/LFE channels (may be empty).
    lfe_channels: list[int] = field(default_factory=list)
    raw: dict = field(default_factory=dict)
    # True when `channels` is our stereo assumption, not the device's own count.
    channels_assumed: bool = False


def list_output_devices() -> list[tuple[int, dict]]:
    """All devices with at least one output channel, as (index, info)."""
    return [
        (index, device)
        for index, device in enumerate(sd.query_devices())
        if int(device.get("max_output_channels", 0)) > 0
    ]


def _hostapi_name(info: dict) -> str:
    try:
        return sd.query_hostapis()[info["hostapi"]]["name"]
    except Exception:
        return "unknown"


def _resolve_index(device) -> tuple[int | None, dict]:
    """Map an index / name-substring / None onto a concrete device info dict."""
    if device is None:
        # Fall back to the default output device.
        info = sd.query_devices(kind="output")
        return info.get("index"), info

    normalized = int(device) if str(device).isdigit() else device
    try:
        info = sd.query_devices(normalized, kind="output")
        idx = info.get("index", normalized if isinstance(normalized, int) else None)
        return idx, info
    except Exception:
        pass

    # Name substring match against output-capable devices.
    name = str(device).lower()
    for index, candidate in list_output_devices():
        if name in str(candidate.get("name", "")).lower():
            return index, candidate

    raise ValueError(f"No output device matched {device!r}.")


def _guess_lfe_channels(name: str, channels: int) -> list[int]:
    """Best-effort sub/LFE detection.

    PortAudio gives us no channel labels, so this is deliberately conservative:
    we only flag a sub channel for the standard 5.1/7.1 interleavings (LFE is
    channel index 3) or when the device name itself mentions a sub. Anything
    else returns ``[]`` and the renderer treats every channel as full-range.
    A future CoreAudio ``AudioChannelLayout`` reader could refine this.
    """
    lowered = name.lower()
    if channels in (6, 8) and ("5.1" in lowered or "7.1" in lowered or channels >= 6):
        # SMPTE/ITU interleave puts LFE at index 3 for 5.1 and 7.1.
        return [3]
    if "sub" in lowered or "lfe" in lowered:
        return [channels - 1]
    return []


def _plausible_channels(channels: int) -> tuple[int, bool]:
    """Resolve a plugin sentinel count to a usable one; ``(channels, assumed)``.

    PortAudio cannot tell us how many speakers are really behind a plugin
    device, so an implausible count means "unknown", and the honest default is
    stereo — what the overwhelming majority of default outputs actually are.
    A real surround rig can still be selected explicitly (``--channels 6``, or
    by naming the hardware device directly).
    """
    if channels <= MAX_PLAUSIBLE_CHANNELS:
        return channels, False
    return ASSUMED_CHANNELS, True


def detect_output(device=None) -> OutputDevice:
    """Resolve and probe an output device into an :class:`OutputDevice`.

    ``device`` may be an index, a name substring, or ``None`` for the system
    default. Never raises for missing labels — only for an unmatched device.
    """
    index, info = _resolve_index(device)
    reported = int(info.get("max_output_channels", 0)) or 1
    channels, assumed = _plausible_channels(reported)
    samplerate = int(info.get("default_samplerate", 0)) or 48000
    name = str(info.get("name", "Unknown"))
    return OutputDevice(
        index=index,
        name=name,
        channels=channels,
        samplerate=samplerate,
        hostapi=_hostapi_name(info),
        lfe_channels=_guess_lfe_channels(name, channels),
        raw=dict(info),
        channels_assumed=assumed,
    )
