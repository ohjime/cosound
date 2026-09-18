import math
from datetime import timedelta

from django.conf import settings
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

from core.models import Listener, ListenerPresence, Player, Sound

VOTE_THROTTLE_WINDOW = timedelta(seconds=getattr(settings, "VOTE_THROTTLE_SECONDS", 60))


def resolve_vote_attribution(player):
    """Find the exposure a vote is about, and say how much to trust the link.

    A vote is only evidence if we know which mix it referred to. The player's
    open exposure is that answer, but only while it still describes what is
    actually playing: an exposure that has been closed, or whose mix key has
    drifted from ``player.playing``, tells us nothing and is dropped rather
    than guessed at.

    Returns ``(exposure_or_None, attribution_quality)``. Today the best
    available grade is ``SERVER_CURRENT`` — the server commanded this mix and
    believes it is playing. Confirming that the speakers actually reached it
    needs an acknowledgement from the player, which nothing sends yet.
    """
    from core.prediction.domain import Mix, MixLayer
    from vote.models import Vote

    exposure = player.current_exposure
    if exposure is None:
        return None, Vote.UNATTRIBUTED

    try:
        playing_mix_key = Mix(
            tuple(
                MixLayer(layer.sound_id, layer.sound_gain)
                for layer in player.playing.layers
                if layer.sound_gain > 0
            )
        ).key
    except ValueError:
        # A mix that cannot even be constructed (a duplicate sound, a gain out
        # of range) cannot be matched against, so treat it as no evidence.
        playing_mix_key = None

    if (
        exposure.player_id != player.pk
        or exposure.ended_at is not None
        or exposure.mix_key != playing_mix_key
    ):
        return None, Vote.UNATTRIBUTED

    if exposure.acknowledged_at is None:
        return exposure, Vote.SERVER_CURRENT
    if (
        exposure.estimated_audible_at is not None
        and timezone.now() < exposure.estimated_audible_at
    ):
        return exposure, Vote.TRANSITION_UNCERTAIN
    return exposure, Vote.PLAYER_ACKNOWLEDGED


def build_vote_context(request):
    token = request.GET.get("player")
    section = request.GET.get("section") or None
    choice = request.GET.get("choice")
    if choice not in ("0", "1"):
        choice = "1"

    player = None
    if token:
        player = (
            Player.objects.select_related("manager", "program__post")
            .filter(token=token)
            .first()
        )

    layers = serialize_player_for_carousel(player, request.user, choice) if player else []

    throttle_seconds_left = 0
    if player and not player.sleeping and layers and request.user.is_authenticated:
        listener = Listener.objects.filter(user=request.user).first()
        if listener:
            throttle_seconds_left = get_throttle_seconds_left(listener)

    return {
        "player": player,
        "sleeping": bool(player and player.sleeping),
        "choice": choice,
        "section": section,
        "layers": layers,
        "throttle_seconds_left": throttle_seconds_left,
    }


def serialize_player_for_carousel(player, user=None, choice=None):
    """Current prediction metadata, without resolving or exposing audio URLs."""
    items = []

    layer_objs = list(player.playing.layers)
    sound_ids = [l.sound_id for l in layer_objs]
    sounds = {
        s.pk: s
        for s in Sound.objects.filter(pk__in=sound_ids).select_related("artist").prefetch_related("tags")
    }

    saved_ids = set()
    if user is not None and user.is_authenticated:
        listener = Listener.objects.filter(user=user).first()
        if listener is not None:
            saved_ids = set(
                listener.collection.filter(pk__in=sound_ids).values_list("pk", flat=True)
            )

    for l in layer_objs:
        sound = sounds.get(l.sound_id)
        if sound is None:
            continue
        items.append(
            {
                "kind": "layer",
                "sound_id": sound.pk,
                "sound_gain": l.sound_gain,
                "sound_title": sound.title,
                "sound_artist": sound.artist_name,
                "artist_url": sound.artist_url,
                "artwork_url": sound.art.url if sound.art else "",
                "gain": int(round(l.sound_gain * 100)),
                "flavor": sound.flavor or "",
                "tags": " / ".join(sound.tags.names()) or "Unknown",
                "saved": sound.pk in saved_ids,
            }
        )
    return items


def local_discussion_context(request, program, page_number=1, form=None):
    from core.discussion import build_discussion_context

    params = request.GET.copy()
    params.pop("page", None)
    query = params.urlencode()
    discussion_url = reverse(
        "vote:discussion", kwargs={"slug": program.post.slug}
    )
    comment_url = reverse(
        "vote:create_comment", kwargs={"slug": program.post.slug}
    )
    return {
        **build_discussion_context(
            program.post,
            request.user,
            page_number,
            form,
            discussion_url=f"{discussion_url}?{query}",
            comment_url=f"{comment_url}?{query}",
            dom_id=f"local-discussion-{program.pk}",
        ),
        "program": program,
    }


def build_vote_page_context(request):
    from core.renderer import render_markdown

    context = build_vote_context(request)
    player = context["player"]
    if player and request.user.is_authenticated:
        record_listener_presence(player, request.user)
    program = (
        player.program
        if player and player.program.post.publication_date
        else None
    )
    context.update(
        program=program,
        body_html=render_markdown(program.post.article) if program else "",
    )
    if program:
        context.update(local_discussion_context(request, program))
    return context


def record_listener_presence(player, user):
    """Keep one bounded activity timestamp per visitor and player."""
    if not user.is_authenticated:
        return None
    listener, _ = Listener.objects.get_or_create(user=user)
    ListenerPresence.objects.update_or_create(
        player=player, listener=listener,
        defaults={"visited_at": timezone.now()},
    )
    return listener


def get_throttle_seconds_left(listener, window: timedelta = VOTE_THROTTLE_WINDOW):
    """Seconds remaining before this listener can vote again (0 if not throttled)."""
    last_vote_at = _last_vote_at(listener)
    if last_vote_at is None:
        return 0
    now = timezone.now()
    if now - last_vote_at >= window:
        return 0
    return math.ceil((last_vote_at + window - now).total_seconds())


def serialize_recent_votes(player, limit=10):
    """Most recent votes at this player, newest first."""
    from vote.models import Vote

    if player is None:
        return []
    votes = (
        Vote.objects.filter(player=player)
        .select_related("voter__user", "player")
        .order_by("-created_at")[:limit]
    )
    now = timezone.now()
    out = []
    for v in votes:
        out.append(
            {
                "id": v.id,
                "voter_username": v.voter.user.username,
                "voter_avatar_url": v.voter.user.avatar_url,
                "player_name": v.player.name,
                "pleasant": v.pleasant,
                "section": v.section or "",
                "seconds_ago": int((now - v.created_at).total_seconds()),
            }
        )
    return out


def _last_vote_at(listener):
    # Imported lazily to avoid a circular import (vote.models -> vote.utils).
    from vote.models import Vote

    return Vote.objects.filter(voter=listener).aggregate(last=Max("created_at"))["last"]
