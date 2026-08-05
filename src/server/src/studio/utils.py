"""Helpers for the studio (studio.cosound.ca) — the artist-facing card creator."""


def get_artist(user):
    """The Artist profile behind a user, or None if they don't have one.

    ``Artist.user`` is a plain FK, so a user can in principle own several artist
    profiles; the studio works against the earliest one.
    """
    if not user or not user.is_authenticated:
        return None

    from core.models import Artist

    return Artist.objects.filter(user=user).order_by("pk").first()


def is_studio_url(url) -> bool:
    """True if a URL points at the studio, on either the subdomain or the path.

    The studio is served two ways: at the root of ``studio.*`` in production
    (see ``config.middleware.SubdomainURLConf``) and under ``/studio/`` on the
    default urlconf for local dev. Login needs to recognise both so it can pick
    the studio's post-login partial.
    """
    if not url:
        return False
    url = url.lower()
    return "//studio." in url or "/studio/" in url or url.rstrip("/").endswith("/studio")
