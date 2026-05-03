import random
from allauth.account.adapter import get_adapter
from django.shortcuts import render
from random_username.generate import generate_username

ANON_EMAIL_DOMAIN = "anon.cosound.ca"

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
