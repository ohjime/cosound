"""Baking a new sound's loop check into the file cosound keeps.

An artist checks a new sound on the LIBRARY card before saving it: it plays
back to back, one copy, while they crop it, crossfade its seam and level it.
Saving makes all three permanent here, in the file itself, so the stored sound
is a loop that runs from its end straight back into its start — it repeats
without a join wherever it is played, with nothing left for a player to apply.

In order:

  1. trim   — keep [trim_start, trim_end] of the upload;
  2. fold   — lay the last `loop_crossfade` seconds over the first, the head
              fading in as the tail fades out, and drop them from the end. This
              is exactly what the web engine does live while the artist listens
              (the same equal-power curves, on passes overlapping by the fade),
              and the same fold the venue player makes with a fixed 50 ms;
  3. level  — move it to the loudness the artist chose, capped at ±24 dB and
              so its loudest sample stays under -1 dBFS;
  4. encode — FLAC, always. It is lossless and knows its exact length; an MP3
              carries encoder delay and padding that would put a gap in the
              seam at every repeat.

The loudness is the engine's reading of the trimmed region, posted with the
files. It is what the artist heard the level against, and measuring it again
here would need a K-weighting filter the server does not otherwise carry; the
two caps are enforced here regardless of what is posted.

Everything streams in blocks. A 50 MB upload can be most of an hour of MP3,
which decoded to float in one piece would be over a gigabyte.
"""

import math
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

import numpy as np
import soundfile as sf
from django.core.files.base import ContentFile

# Where a new sound is levelled to unless the artist nudges it: the venue
# player's conditioning target (src/player conditioning.py TARGET_LUFS), and the
# web engine's DEFAULT_LOUDNESS_TARGET.
HOUSE_LOUDNESS_LUFS = -20.0
# How far either way an artist may nudge it (LOUDNESS_NUDGE_LU in the engine).
LOUDNESS_NUDGE_LU = 6.0
# The most levelling may move a sound, either way (LOUDNESS_GAIN_LIMIT_DB).
GAIN_LIMIT_DB = 24.0
# The loudest a sample may end up (PEAK_CEILING_DB in the engine).
PEAK_CEILING_DBFS = -1.0
# The shortest crop a sound may be left with (MIN_REGION_SECONDS).
MIN_REGION_SECONDS = 0.25
# Anything under this is no gain at all, and not worth re-encoding a FLAC for.
UNITY_DB = 0.05

BLOCK_FRAMES = 65_536
# Subtypes worth keeping 24 bits of; anything else is written at 16.
DEEP_SUBTYPES = {"PCM_24", "PCM_32", "FLOAT", "DOUBLE"}


@dataclass(frozen=True)
class BakedSound:
    content: ContentFile
    duration: float
    trim_start: float
    trim_end: float
    loop_crossfade: float
    loudness_lufs: float | None
    loudness_gain_db: float


def crop_seconds(total, trim_start=0.0, trim_end=None):
    """The kept region of a file `total` seconds long, as (start, end).

    The engine's cropRegion, so the bake keeps what the artist heard kept: a
    start dragged past its end backs off to leave MIN_REGION_SECONDS, and an end
    past the file is the end of the file.
    """
    total = max(0.0, float(total))
    shortest = min(MIN_REGION_SECONDS, total)
    end = total if trim_end is None else min(total, max(0.0, float(trim_end)))
    start = min(max(0.0, float(trim_start or 0.0)), max(0.0, end - shortest))
    return start, max(end, start + shortest)


def level_gain_db(loudness, target, peak):
    """The gain that moves `loudness` to `target`, within both caps.

    Zero when there is no reading to go on. `peak` is the loudest sample of
    what is being levelled, linear, so the result never lifts it past
    PEAK_CEILING_DBFS.
    """
    if loudness is None or target is None or not math.isfinite(loudness):
        return 0.0
    gain = max(-GAIN_LIMIT_DB, min(GAIN_LIMIT_DB, float(target) - float(loudness)))
    if peak > 0:
        gain = min(gain, PEAK_CEILING_DBFS - 20 * math.log10(peak))
    return gain


def _read(sound, frame, count):
    """`count` frames from `frame` on, as float32, padded with silence past EOF."""
    sound.seek(frame)
    block = sound.read(count, dtype="float32", always_2d=True)
    if block.shape[0] < count:
        padding = np.zeros((count - block.shape[0], sound.channels), dtype=np.float32)
        block = np.concatenate([block, padding])
    return block


def _blocks(sound, start, end, fold):
    """The baked file's samples, before levelling, a block at a time.

    First the seam — the region's head fading in over its tail fading out, the
    same sin/cos pair the engine's FADE_IN / FADE_OUT curves are — then the rest
    of the region up to where that tail began.
    """
    for offset in range(0, fold, BLOCK_FRAMES):
        count = min(BLOCK_FRAMES, fold - offset)
        head = _read(sound, start + offset, count)
        tail = _read(sound, end - fold + offset, count)
        phase = (np.arange(offset, offset + count, dtype=np.float64) / fold)[:, None]
        phase *= math.pi / 2
        yield (head * np.sin(phase) + tail * np.cos(phase)).astype(np.float32)
    for offset in range(start + fold, end - fold, BLOCK_FRAMES):
        yield _read(sound, offset, min(BLOCK_FRAMES, end - fold - offset))


def bake_sound(
    upload,
    *,
    trim_start=0.0,
    trim_end=None,
    loop_crossfade=0.0,
    loudness=None,
    target=HOUSE_LOUDNESS_LUFS,
):
    """Trim, fold and level an uploaded sound, and encode it as FLAC.

    Raises ValueError when the upload cannot be read as audio; the form has
    already made sure it can (core.validators.validate_sound).
    """
    upload.seek(0)
    name = f"{PurePath(getattr(upload, 'name', '') or 'sound').stem}.flac"
    with sf.SoundFile(upload) as sound:
        rate = sound.samplerate
        start_s, end_s = crop_seconds(sound.frames / rate, trim_start, trim_end)
        start, end = round(start_s * rate), min(sound.frames, round(end_s * rate))
        fold = min(round(max(0.0, float(loop_crossfade or 0.0)) * rate), (end - start) // 2)

        peak = 0.0
        for block in _blocks(sound, start, end, fold):
            if block.size:
                peak = max(peak, float(np.max(np.abs(block))))
        gain_db = level_gain_db(loudness, target, peak)

        untouched = start == 0 and end == sound.frames and fold == 0 and abs(gain_db) < UNITY_DB
        if untouched and sound.format == "FLAC":
            upload.seek(0)
            content = ContentFile(upload.read(), name=name)
        else:
            subtype = "PCM_24" if sound.subtype in DEEP_SUBTYPES else "PCM_16"
            scale = np.float32(10 ** (gain_db / 20))
            buffer = BytesIO()
            with sf.SoundFile(
                buffer,
                mode="w",
                samplerate=rate,
                channels=sound.channels,
                format="FLAC",
                subtype=subtype,
            ) as out:
                for block in _blocks(sound, start, end, fold):
                    out.write(block * scale)
            content = ContentFile(buffer.getvalue(), name=name)

    return BakedSound(
        content=content,
        duration=(end - start - fold) / rate,
        trim_start=start_s,
        trim_end=end_s,
        loop_crossfade=fold / rate,
        loudness_lufs=None if loudness is None else float(loudness) + gain_db,
        loudness_gain_db=gain_db,
    )
