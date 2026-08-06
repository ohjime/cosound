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


@dataclass
class OutputDevice:
    """What we can reliably learn about a selected output device."""

    index: int | None  # None == system default output
    name: str
    channels: int  # max_output_channels
    samplerate: int  # device default sample rate
    hostapi: str
    # Best-effort: indices we believe are sub/LFE channels (may be empty).
    lfe_channels: list[int] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def list_output_devices() -> list[tuple[int, dict]]:
    """All devices with at least one output channel, as (index, info)."""
    return [
        (index, device)
        for index, device in enumerate(sd.query_devices())
        if int(device.get("max_output_channels", 0)) > 0
    ]


def list_input_devices() -> list[tuple[int, dict]]:
    """All devices with at least one input channel, as (index, info)."""
    return [
        (index, device)
        for index, device in enumerate(sd.query_devices())
        if int(device.get("max_input_channels", 0)) > 0
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


def detect_output(device=None) -> OutputDevice:
    """Resolve and probe an output device into an :class:`OutputDevice`.

    ``device`` may be an index, a name substring, or ``None`` for the system
    default. Never raises for missing labels — only for an unmatched device.
    """
    index, info = _resolve_index(device)
    channels = int(info.get("max_output_channels", 0)) or 1
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
    )


@dataclass
class InputDevice:
    """What we can reliably learn about a selected input (microphone) device."""

    index: int | None  # None == system default input
    name: str
    channels: int  # max_input_channels
    samplerate: int  # device default sample rate
    hostapi: str
    raw: dict = field(default_factory=dict)


def _resolve_input_index(device) -> tuple[int | None, dict]:
    """Map an index / name-substring / None onto a concrete input device info dict."""
    if device is None:
        info = sd.query_devices(kind="input")
        return info.get("index"), info

    normalized = int(device) if str(device).isdigit() else device
    try:
        info = sd.query_devices(normalized, kind="input")
        idx = info.get("index", normalized if isinstance(normalized, int) else None)
        return idx, info
    except Exception:
        pass

    name = str(device).lower()
    for index, candidate in list_input_devices():
        if name in str(candidate.get("name", "")).lower():
            return index, candidate

    raise ValueError(f"No input device matched {device!r}.")


def detect_input(device=None) -> InputDevice | None:
    """Resolve and probe a microphone into an :class:`InputDevice`.

    Unlike :func:`detect_output`, a microphone is optional: this returns
    ``None`` (never raises) when no matching input device is available, so
    callers can gracefully disable mic-driven features.
    """
    try:
        index, info = _resolve_input_index(device)
    except Exception:
        return None

    channels = int(info.get("max_input_channels", 0))
    if channels <= 0:
        return None

    samplerate = int(info.get("default_samplerate", 0)) or 48000
    name = str(info.get("name", "Unknown"))
    return InputDevice(
        index=index,
        name=name,
        channels=channels,
        samplerate=samplerate,
        hostapi=_hostapi_name(info),
        raw=dict(info),
    )
