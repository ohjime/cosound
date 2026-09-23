"""Validation shared by server-managed player audio uploads."""

import numpy as np
import soundfile as sf
from django.core.exceptions import ValidationError


CHIME_MAX_BYTES = 5 * 1024 * 1024
CHIME_MAX_SECONDS = 5


def validate_chime(upload):
    """Reject files the physical player cannot safely use as a one-shot."""
    # ModelForm validation also revisits unchanged FieldFiles. They were
    # validated when uploaded; downloading them again from object storage would
    # make an unrelated Player Program edit depend on media availability.
    if getattr(upload, "_committed", False):
        return
    if upload.size > CHIME_MAX_BYTES:
        raise ValidationError("Chime must be 5 MB or smaller.")

    try:
        original_position = upload.tell()
    except (AttributeError, OSError, ValueError):
        original_position = 0

    audio = None
    validation_error = None
    try:
        upload.seek(0)
        audio = sf.SoundFile(upload)
        if audio.samplerate <= 0 or audio.frames <= 0:
            validation_error = ValidationError("Chime cannot be empty.")
        elif audio.frames > audio.samplerate * CHIME_MAX_SECONDS:
            validation_error = ValidationError("Chime must be 5 seconds or shorter.")
        else:
            has_audio = False
            for block in audio.blocks(
                blocksize=65_536,
                dtype="float32",
                always_2d=True,
            ):
                if not np.isfinite(block).all():
                    validation_error = ValidationError(
                        "Chime contains invalid audio samples."
                    )
                    break
                # Match the physical player's channel-average downmix. An
                # anti-phase stereo upload otherwise passes here but becomes
                # complete silence at playback time.
                mono = np.mean(block, axis=1, dtype=np.float32)
                has_audio = has_audio or bool(np.any(mono))
            if validation_error is None and not has_audio:
                validation_error = ValidationError("Chime must contain audible audio.")
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise ValidationError(
            "Upload a valid WAV, FLAC, OGG, MP3, or AIFF audio file."
        ) from error
    finally:
        if audio is not None:
            audio.close()
        try:
            upload.seek(original_position)
        except (AttributeError, OSError, ValueError):
            pass

    if validation_error is not None:
        raise validation_error


SOUND_MAX_BYTES = 50 * 1024 * 1024


def validate_sound(upload):
    """Reject an artist's upload that the players could not decode.

    Lighter than the chime's check: a sound is meant to be long and may be
    quiet, so this only proves the file opens as audio and holds some. The
    decode is libsndfile's, the same one the physical player uses, which is
    why a format a browser happens to play (AAC, say) is still refused.
    """
    if upload.size > SOUND_MAX_BYTES:
        raise ValidationError("Sound must be 50 MB or smaller.")
    try:
        original_position = upload.tell()
    except (AttributeError, OSError, ValueError):
        original_position = 0
    try:
        upload.seek(0)
        with sf.SoundFile(upload) as audio:
            empty = audio.samplerate <= 0 or audio.frames <= 0
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise ValidationError(
            "Upload a valid WAV, FLAC, OGG, MP3, or AIFF audio file."
        ) from error
    finally:
        try:
            upload.seek(original_position)
        except (AttributeError, OSError, ValueError):
            pass
    if empty:
        raise ValidationError("Sound cannot be empty.")
