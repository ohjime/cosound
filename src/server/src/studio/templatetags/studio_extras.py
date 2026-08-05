from django import template

from studio.utils import get_artist

register = template.Library()


@register.simple_tag(takes_context=True)
def studio_artist(context):
    """The requesting user's Artist profile, or None.

    Lets the ``#stage`` partial resolve its own gating state, so it renders
    correctly from any view — including ``login.views`` rendering it as the
    post-login partial, which has no studio context of its own.
    """
    request = context.get("request")
    return get_artist(request.user) if request else None
