from django import template

from core.utils import generate_random_stranger, generate_random_welcome, get_artist

register = template.Library()


@register.simple_tag
def welcome_phrase():
    return generate_random_welcome()


@register.simple_tag
def stranger_phrase():
    return generate_random_stranger()


@register.simple_tag(takes_context=True)
def artist_profile(context):
    """The requesting user's Artist profile, or None.

    Lets a partial resolve for itself whether the viewer is an artist, so it
    renders the same from its own view and from login's post-login swap, which
    has no such context of its own.
    """
    request = context.get("request")
    return get_artist(request.user) if request else None
