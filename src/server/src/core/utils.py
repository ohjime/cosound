from django.conf import settings
from django.utils.module_loading import import_string


def _get_sound_dimension():
    sound_dim_path = getattr(settings, "COSOUND_SOUND_DIMENSION", None)
    if sound_dim_path:
        try:
            return import_string(sound_dim_path)
        except ImportError:
            pass
    # Fallback to core default
    from core.classify import sound_dimension

    return sound_dimension


def _get_sound_classifier():
    sound_classifier_path = getattr(settings, "COSOUND_SOUND_CLASSIFIER", None)
    if sound_classifier_path:
        try:
            return import_string(sound_classifier_path)
        except ImportError:
            pass
    # Fallback to core default
    from core.classify import random_sound_classifier

    return random_sound_classifier


def _get_listener_dimension():
    listener_dim_path = getattr(settings, "COSOUND_LISTENER_DIMENSION", None)
    if listener_dim_path:
        try:
            return import_string(listener_dim_path)
        except ImportError:
            pass
    # Fallback to core default
    from core.classify import listener_dimension

    return listener_dimension


def _get_listener_classifier():
    listener_classifier_path = getattr(settings, "COSOUND_LISTENER_CLASSIFIER", None)
    if listener_classifier_path:
        try:
            return import_string(listener_classifier_path)
        except ImportError:
            pass
    # Fallback to core default
    from core.classify import random_listener_classifier

    return random_listener_classifier
