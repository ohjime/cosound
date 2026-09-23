import random

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.module_loading import import_string


WELCOME_PHRASES = [
    "They're Back",
    "Welcome Back",
    "Look Who's Here",
    "Good To See You",
    "Hey Stranger",
    "Long Time No See",
    "The Legend Returns",
    "Right On Time",
]

STRANGER_PHRASES = [
    "Hello Stranger",
    "Who Goes There",
    "New Face",
    "Just Passing Through",
    "First Time?",
    "Welcome In",
    "Step Right Up",
]


def generate_random_welcome():
    return random.choice(WELCOME_PHRASES)


def generate_random_stranger():
    return random.choice(STRANGER_PHRASES)


def add_card(target_deck, template, request, context=None):
    """
    Return an htmx response that appends a rendered card into a deck.

    Usage in any htmx view:
        return add_card("deck", "myapp/card.html#card", request, context)

    The HX-Retarget / HX-Reswap response headers redirect htmx to inject
    the rendered content into #{target_deck} with beforeend, regardless of
    what hx-target / hx-swap the triggering element declared.
    """
    response = render(request, template, context or {})
    response["HX-Retarget"] = f"#{target_deck}"
    response["HX-Reswap"] = "beforeend"
    return response


def pop_card(request, template=None, context=None, reswap=None):
    """
    Return a response that triggers the card containing the htmx element
    to animate out and remove itself from the DOM.

    Fires a `card:remove` event on the triggering element via HX-Trigger.
    The event bubbles up to the enclosing c-core-card, which handles the
    exit animation and DOM removal via Alpine.js.

    Optionally pass a template (+ context) whose body contains one or more
    `hx-swap-oob` elements to simultaneously update other parts of the page.
    Pass reswap to override the triggering element's hx-swap (defaults to
    "none" so the main swap is suppressed when OOB content is used).

    Usage:
        # Simple pop
        return pop_card(request)

        # Pop + OOB updates defined in the template
        return pop_card(request, template="game/post_save_oob.html", context=ctx)

        # Pop + keep the triggering element's own hx-swap behaviour
        return pop_card(request, template="...", reswap="innerHTML")
    """
    if template:
        response = render(request, template, context or {})
    else:
        response = HttpResponse("")

    response["HX-Reswap"] = reswap or "none"
    response["HX-Trigger"] = "card:remove"
    return response


def close_modal(request, template=None, context=None, reswap=None):
    """
    Return a response that closes the base modal (#core_modal).

    Fires a `close-modal` event which the JS listener in base.html catches
    to call dialog.close(). The native close animation plays automatically.

    Optionally pass a template (+ context) whose body contains one or more
    `hx-swap-oob` elements to simultaneously update other parts of the page.
    Pass reswap to override the triggering element's hx-swap (defaults to
    "none" so the main swap is suppressed when OOB content is used).

    Usage:
        # Simple close
        return close_modal(request)

        # Close + OOB updates defined in the template
        return close_modal(request, template="game/post_action_oob.html", context=ctx)
    """
    if template:
        response = render(request, template, context or {})
    else:
        response = HttpResponse("")

    response["HX-Reswap"] = reswap or "none"
    response["HX-Trigger"] = "close-modal"
    return response


def show_modal(request, template, context=None):
    """
    Return an htmx response that injects rendered content into the base modal
    and opens it.

    Usage in any htmx view:
        return show_modal(request, "myapp/modal_content.html", context)

    The base modal dialog (#core_modal) lives in core/base.html and listens
    for the 'show-modal' event to call showModal(). HX-Trigger-After-Swap
    fires that event once the content is swapped into #core_modal_content.
    """
    response = render(request, template, context or {})
    response["HX-Retarget"] = "#core_modal_content"
    response["HX-Reswap"] = "innerHTML"
    response["HX-Trigger-After-Swap"] = "show-modal"
    return response


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


def get_random_avatar_url(seed):
    """Deterministic dicebear avatar URL keyed by user pk (or any seed)."""
    colors = ["b6e3f4", "c0aede", "ffdfbf"]
    color = colors[int(seed) % len(colors)]
    return (
        f"https://api.dicebear.com/10.x/line-face/svg?backgroundColor={color}&seed={seed}"
    )


def generate_layers_string(layers, with_gain=True) -> str:
    """The key a Cosound is hashed from: `id@gain` per layer, joined by `&`.

    Layers are `(sound_id, gain)` pairs or core.layers.LayerSpecs. A spec whose
    timing is not the default adds it after its gain (LayerSpec.timing_key);
    one at the defaults adds nothing, which is what keeps every mix saved
    before layers had timing hashing exactly as it did. `with_gain=False` is
    the gain- and timing-blind key Cosound.hashset is made of.
    """
    parts = []
    for layer in layers:
        if isinstance(layer, tuple):
            (sid, g), timing = layer, ""
        else:
            sid, g, timing = layer.sound_id, layer.gain, layer.timing_key()
        parts.append(f"{sid}@{g}{timing}" if with_gain else f"{sid}@?")
    return "&".join(parts)


def get_artist(user):
    """The Artist profile behind a user, or None if they don't have one.

    ``Artist.user`` is a plain FK, so a user can in principle own several
    artist profiles; everything artist-only works against the earliest one.
    """
    if not user or not user.is_authenticated:
        return None

    from core.models import Artist

    return Artist.objects.filter(user=user).order_by("pk").first()
