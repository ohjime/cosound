"""Prepare the short, centred acknowledgement played when a vote arrives."""

import numpy as np
import soundfile as sf

from app.conditioning import _resample


VOTE_CHIME_SECONDS_LIMIT = 5.0
# Keep uploaded sounds no louder than the built-in tone.  Vote bursts are mixed
# over the soundscape and deliberately bypass its spatial/reverb buses, so a
# conservative ceiling leaves useful headroom before the final hard clip.
VOTE_CHIME_PEAK = 0.145


def vote_chime(sample_rate):
    t = np.arange(round(sample_rate * 0.45), dtype=np.float64) / sample_rate
    attack = np.minimum(t / 0.006, 1.0)
    release = np.minimum((0.45 - t) / 0.04, 1.0)
    tone = (
        np.sin(2 * np.pi * 880 * t) * np.exp(-9 * t)
        + 0.35 * np.sin(2 * np.pi * 1320 * t) * np.exp(-13 * t)
    )
    return (0.12 * tone * attack * release).astype(np.float32)


def load_vote_chime(path: str, sample_rate: int) -> np.ndarray:
    """Decode an uploaded one-shot into the callback's mono float32 format.

    This intentionally does not use ``condition_file``.  That pipeline repairs
    loop seams by folding a file's tail into its head, which is desirable for
    ambience loops but would alter and shorten a one-shot acknowledgement.
    """
    if sample_rate <= 0:
        raise ValueError("Vote chime output sample rate must be positive")

    info = sf.info(path)
    if info.samplerate <= 0 or info.frames <= 0:
        raise ValueError("Vote chime is empty or has no sample rate")
    if info.frames / info.samplerate > VOTE_CHIME_SECONDS_LIMIT:
        raise ValueError(
            f"Vote chime must be at most {VOTE_CHIME_SECONDS_LIMIT:g} seconds"
        )

    # Read at most one frame beyond the limit as a second guard against a
    # malformed container whose header reports an incorrect duration.
    max_frames = round(info.samplerate * VOTE_CHIME_SECONDS_LIMIT)
    data, source_rate = sf.read(
        path, frames=max_frames + 1, dtype="float32", always_2d=True
    )
    if len(data) == 0:
        raise ValueError("Vote chime is empty")
    if len(data) > max_frames:
        raise ValueError(
            f"Vote chime must be at most {VOTE_CHIME_SECONDS_LIMIT:g} seconds"
        )
    if not np.isfinite(data).all():
        raise ValueError("Vote chime contains non-finite samples")

    # The callback centres a mono acknowledgement across every output layout.
    # Averaging retains the expected level for ordinary mono/stereo uploads.
    mono = np.mean(data, axis=1, dtype=np.float32)[:, np.newaxis]
    mono = _resample(mono, source_rate, sample_rate)[:, 0]
    if not np.isfinite(mono).all():
        raise ValueError("Vote chime contains non-finite samples")

    peak = float(np.max(np.abs(mono))) if mono.size else 0.0
    if peak <= 0.0:
        raise ValueError("Vote chime is silent")
    if peak > VOTE_CHIME_PEAK:
        mono = mono * (VOTE_CHIME_PEAK / peak)
    return np.ascontiguousarray(mono, dtype=np.float32)
