import random

from django.contrib.auth import login
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render

from core.models import Listener, Sound, User
from home.utils import generate_sound_artwork
from vote.adapters import UnifiedRequestLoginCodeForm
from vote.utils import (
    clear_login_state,
    generate_random_welcome,
    get_login_state,
    get_random_avatar_url,
    send_login_code,
)


def home_index(request):
    return render(request, "home/index.html")


def load(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    sound_ids = list(Sound.objects.order_by("?")[:8].values_list("id", flat=True))
    sounds = [
        {
            **sound.asLayer(with_gain=round(random.uniform(0.1, 0.9), 2)).model_dump(),
            "artwork_url": generate_sound_artwork(sound),
            "mute": False,
            "flavor": sound.flavor or "",
            "tags": " / ".join(sound.tags.names()) or "Unknown",
        }
        for sound in Sound.objects.filter(id__in=sound_ids).prefetch_related("tags")
    ]
    for sound in sounds[2:]:
        sound["mute"] = True

    return render(
        request,
        "home/index.html#home_player",
        {"sounds": sounds},
    )


def _serialize_sounds(sounds):
    return [
        {
            **sound.asLayer(with_gain=0.5).model_dump(),
            "gain": 50,
            "mute": False,
            "flavor": sound.flavor or "",
            "tags": " / ".join(sound.tags.names()) or "Unknown",
            "artwork_url": generate_sound_artwork(sound),
            "id": sound.id,
            "title": sound.title,
            "artist": sound.artist,
        }
        for sound in sounds
    ]


def swap(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    sounds = _serialize_sounds(Sound.objects.prefetch_related("tags").order_by("?")[:5])
    return render(request, "home/index.html#swap_view", {"sounds": sounds})


def search(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    q = (request.GET.get("q") or "").strip()
    qs = Sound.objects.prefetch_related("tags")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(artist__icontains=q)).order_by(
            "title"
        )[:20]
    else:
        qs = qs.order_by("?")[:5]
    return render(
        request,
        "home/index.html#sound_list_items",
        {"sounds": _serialize_sounds(qs)},
    )


def carousel(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(request, "home/index.html#carousel_view")


def _collect_alert(request, msg, alert_type="alert-error"):
    response = render(
        request,
        "home/index.html#collect_alert",
        {"alert_msg": msg, "alert_type": alert_type},
    )
    response["HX-Retarget"] = "#collect-login-alerts"
    response["HX-Reswap"] = "afterbegin"
    return response


def _auth_context(user):
    return {
        "avatar_url": get_random_avatar_url(user.pk),
        "username": user.username,
        "welcome_text": generate_random_welcome(),
    }


def collect_check_email(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    form = UnifiedRequestLoginCodeForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        try:
            send_login_code(request, email)
        except Exception:
            return _collect_alert(
                request,
                "Failed to send login code. Please try again later.",
                "alert-warning",
            )
        return render(request, "home/index.html#collect_code_form")

    email_errors = form.errors.get("email")
    return _collect_alert(
        request,
        email_errors[0] if email_errors else "This email address can not be used.",
        "alert-info",
    )


def collect_check_code(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    email, correct_code = get_login_state(request)
    if not email or not correct_code:
        return _collect_alert(
            request,
            "Login session expired. Please request a new code.",
            "alert-warning",
        )

    if request.method == "POST":
        input_code = request.POST.get("code", "").strip()
        if input_code == str(correct_code):
            try:
                user = User.objects.get(email__iexact=email)
                Listener.objects.get_or_create(user=user)
                login(
                    request, user, backend="django.contrib.auth.backends.ModelBackend"
                )
                clear_login_state(request)
                return render(
                    request, "home/index.html#collect_success", _auth_context(user)
                )
            except User.DoesNotExist:
                return _collect_alert(
                    request, "User not found for this login code.", "alert-error"
                )

    return _collect_alert(request, "Invalid or expired code.", "alert-error")


def collect_cancel(request):
    clear_login_state(request)
    return HttpResponse(status=204)
