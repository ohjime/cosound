import math
import random
from datetime import timedelta

from allauth.account.adapter import get_adapter
from django.conf import settings
from django.db.models import Max
from django.shortcuts import render
from django.utils import timezone
from random_username.generate import generate_username

from core.models import Listener, Player, User


ANON_EMAIL_DOMAIN = "anon.cosound.ca"

VOTE_THROTTLE_WINDOW = timedelta(seconds=getattr(settings, "VOTE_THROTTLE_SECONDS", 60))

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


def generate_random_welcome():
    return random.choice(WELCOME_PHRASES)


def send_login_code(request, email):
    adapter = get_adapter(request)
    code = adapter.generate_login_code()
    adapter.send_mail("account/email/login_code", email, {"code": code})
    request.session["login_code"] = code
    request.session["login_email"] = email


def get_login_state(request):
    return (
        request.session.get("login_email"),
        request.session.get("login_code"),
    )


def clear_login_state(request):
    request.session.pop("login_code", None)
    request.session.pop("login_email", None)


def build_authenticated_vote_context(request, user):
    listener, _ = Listener.objects.get_or_create(user=user)
    time_left = get_throttle_seconds_left(listener)
    context = get_vote_context(request)
    context["time_left"] = time_left
    context["avatar_url"] = get_random_avatar_url(user.pk)
    context["username"] = user.username
    context["welcome_text"] = generate_random_welcome()
    return context, time_left


def get_vote_context(request):
    token = request.GET.get("player")
    section = request.GET.get("section") or None
    choice = request.GET.get("choice")

    player = None
    if token:
        player = Player.objects.select_related("account").filter(token=token).first()

    return {
        "player": player,
        "player_name": player.name if player else None,
        "player_photo_url": (player.photo.url if player and player.photo else None),
        "manager_name": player.account.name if player else None,
        "manager_logo_url": (
            player.account.logo.url
            if player and player.account and player.account.logo
            else None
        ),
        "choice": choice,
        "section": section,
    }


def raise_alert(request, alert_msg, alert_type="alert-error"):
    response = render(
        request,
        "vote/index.html#alert",
        {
            "alert_type": alert_type,
            "alert_msg": alert_msg,
        },
    )
    # THIS IS THE MAGIC: Tells HTMX to ignore the original `hx-target="#index"`
    response["HX-Retarget"] = "#vote_alerts"
    response["HX-Reswap"] = "afterbegin"
    return response


def generate_anon_username():
    """Return a single random username (e.g. 'BraveOwl42')."""
    return generate_username(1)[0]


def generate_anon_email(username):
    """Return an @anon.cosound.ca email tied to the given username."""
    return f"{username}@{ANON_EMAIL_DOMAIN}"


def is_anonymous_user(user):
    """A user is 'anonymous' if it was minted via the guest login flow."""
    if user.is_anonymous:
        return True
    if user.is_authenticated and user.email:
        return user.email.endswith(f"@{ANON_EMAIL_DOMAIN}")
    return False


def get_random_avatar_url(seed):
    """Deterministic dicebear avatar URL keyed by user pk (or any seed)."""
    colors = ["b6e3f4", "c0aede", "ffdfbf"]
    color = colors[int(seed) % len(colors)]
    return (
        f"https://api.dicebear.com/9.x/micah/svg?seed={seed}"
        f"&backgroundColor={color}&scale=110&translateY=-7"
    )


def get_throttle_seconds_left(listener, window: timedelta = VOTE_THROTTLE_WINDOW):
    """Seconds remaining before this listener can vote again (0 if not throttled)."""
    last_vote_at = _last_vote_at(listener)
    if last_vote_at is None:
        return 0
    now = timezone.now()
    if now - last_vote_at >= window:
        return 0
    return math.ceil((last_vote_at + window - now).total_seconds())


def _last_vote_at(listener):
    # Imported lazily to avoid a circular import (vote.models -> vote.utils).
    from vote.models import Vote

    return Vote.objects.filter(voter=listener).aggregate(last=Max("created_at"))["last"]
