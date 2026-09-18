"""Prepare the short, centred acknowledgement played when a vote arrives."""

import numpy as np
import soundfile as sf

from app.conditioning import _resample


VOTE_CHIME_SECONDS_LIMIT = 5.0
# How the prepared buffers are stored.  This is a working level, not a limit on
# how loud a chime may sound: the player re-levels whatever is installed against
# the mix at playback, measuring the buffer it was actually given.  Storing
# every chime at one level keeps the degrees of the scale in balance with each
# other and keeps an upload from arriving at full scale.
VOTE_CHIME_PEAK = 0.145

# The chime is levelled against the soundscape rather than against full scale,
# and loudness is compared with loudness: the player matches the one-shot's
# short-term RMS to the program's volume setting times the mix's own running
# RMS.  Peak-against-RMS was the earlier mistake here -- the tone's crest factor
# is about 2.5, so aiming its *peak* at the mix's level left it audibly under
# the soundscape even at maximum.
VOTE_CHIME_RMS_SECONDS = 2.0
# Measure the one-shot over the window it is actually sounding in.  Averaged
# over its whole length instead, a chime's decay tail -- or the silence at the
# end of a five-second upload -- would read as quiet and be turned up to match.
VOTE_CHIME_RMS_WINDOW_SECONDS = 0.1
# Below this the mix stops being a useful reference: a sleeping or silent room
# would scale every acknowledgement to nothing.  Votes still arrive then, and
# they still have to be heard, so the reference never falls below this.
VOTE_CHIME_RMS_FLOOR = 0.05
# What volume 1.0 means, as a multiple of the mix's own level.  Parity with the
# soundscape sits at 0.25, which is already a clear acknowledgement; the rest of
# the range is there for a room that needs to hear it over everything, and four
# times is about what the output can carry before a single chime clips.
VOTE_CHIME_MAX_RATIO = 4.0
# The real headroom limit, replacing the fixed ceiling the chime used to sit
# under.  A burst may still reach the clipper -- eight voices can overlap -- but
# one acknowledgement at full volume must not, whatever the mix is doing.
VOTE_CHIME_OUTPUT_CEILING = 0.7
# What to use until the first `/player` snapshot lands, which then replaces it
# with the Player Program's own setting.  Matches COSOUND_CHIME_VOLUME.
VOTE_CHIME_DEFAULT_VOLUME = 0.5

# C major pentatonic stays consonant even when several votes overlap.  The
# lower octave is reserved for downvotes; upvotes use the same notes in the
# middle register.  A notification without polarity may use either octave.
VOTE_CHIME_SCALE = (-12, -10, -8, -5, -3, 0, 2, 4, 7, 9)
VOTE_CHIME_DOWNVOTE_DEGREES = tuple(range(5))
VOTE_CHIME_UPVOTE_DEGREES = tuple(range(5, 10))
VOTE_CHIME_ROOT_HZ = 261.625565  # C4; the bottom note is C3.
# The built-in tone's second partial, a perfect fifth up.  Held as a ratio so
# transposing moves the whole timbre instead of detuning it.
VOTE_CHIME_PARTIAL = 1.5


def chime_loudness(samples, sample_rate):
    """Loudest short window of a prepared one-shot, as RMS.

    This is what gets matched against the mix, so it has to describe how loud
    the chime sounds rather than how loud its loudest sample is, and it has to
    ignore whatever silence follows the sound.
    """
    mono = np.asarray(samples, dtype=np.float32)
    if mono.size == 0:
        return 0.0
    window = max(1, round(sample_rate * VOTE_CHIME_RMS_WINDOW_SECONDS))
    if mono.size <= window:
        return float(np.sqrt(np.mean(np.square(mono), dtype=np.float64)))
    # One pass: the running sum of squares gives every window's energy, and the
    # largest of those is the level the chime is heard at.
    energy = np.concatenate(
        ([0.0], np.cumsum(np.square(mono, dtype=np.float64)))
    )
    windows = (energy[window:] - energy[:-window]) / window
    return float(np.sqrt(np.max(windows)))


def _pitch_ratio(semitones):
    """Frequency multiplier for an equal-tempered interval."""
    return 2.0 ** (semitones / 12.0)


def vote_chime(sample_rate, semitones=0):
    """Synthesise the built-in tone at one degree of the scale."""
    root = VOTE_CHIME_ROOT_HZ * _pitch_ratio(semitones)
    t = np.arange(round(sample_rate * 0.45), dtype=np.float64) / sample_rate
    attack = np.minimum(t / 0.006, 1.0)
    release = np.minimum((0.45 - t) / 0.04, 1.0)
    tone = (
        np.sin(2 * np.pi * root * t) * np.exp(-9 * t)
        + 0.35 * np.sin(2 * np.pi * root * VOTE_CHIME_PARTIAL * t) * np.exp(-13 * t)
    )
    return (0.12 * tone * attack * release).astype(np.float32)


def transpose_chime(samples, semitones, sample_rate):
    """Repitch a prepared one-shot, the way a sampler would.

    An upload is a fixed recording, so its degrees have to come from replaying
    it at a different speed. Resampling to ``sample_rate / ratio`` and handing the
    result to a stream running at ``sample_rate`` is exactly that, and it lets
    the resampler band-limit the result instead of aliasing.  Lower notes take
    longer, so trim the prepared buffer to the upload's five-second limit.
    """
    mono = np.asarray(samples, dtype=np.float32)
    if semitones == 0:
        # Copy rather than alias: the caller keeps its array, and the audio
        # thread reads this one without a lock on the source.
        return np.array(mono, dtype=np.float32, order="C", copy=True)
    target = round(sample_rate / _pitch_ratio(semitones))
    shifted = _resample(mono[:, np.newaxis], sample_rate, target)[:, 0]
    limit = round(sample_rate * VOTE_CHIME_SECONDS_LIMIT)
    if len(shifted) > limit:
        shifted = shifted[:limit].copy()
        # A long upload can still be sounding at the cutoff after pitching down.
        fade = min(round(sample_rate * 0.02), limit)
        shifted[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    # Band-limiting a transient rings above the source peak -- measured at up to
    # a quarter over on a square-edged one-shot.  Re-apply the ceiling so every
    # degree keeps the headroom the root was given, eight-deep at the clipper.
    peak = float(np.max(np.abs(shifted))) if shifted.size else 0.0
    if peak > VOTE_CHIME_PEAK:
        shifted = shifted * (VOTE_CHIME_PEAK / peak)
    return np.ascontiguousarray(shifted, dtype=np.float32)


def vote_chime_scale(sample_rate, samples=None):
    """Render every degree of the scale, or the built-in tone's degrees.

    The whole scale is built up front because the audio callback cannot afford
    to synthesise or resample: it picks an already-finished buffer and mixes it.
    """
    if samples is None:
        return tuple(
            vote_chime(sample_rate, semitones) for semitones in VOTE_CHIME_SCALE
        )
    return tuple(
        transpose_chime(samples, semitones, sample_rate)
        for semitones in VOTE_CHIME_SCALE
    )


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
