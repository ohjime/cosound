import uuid
from django.contrib.auth import login, get_user_model
from django.shortcuts import redirect, render
from random_username.generate import generate_username
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from allauth.account.adapter import get_adapter
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta

from core.models import Player, Sound, User

from voter.models import Voter, Vote
from voter.adapters import UnifiedRequestLoginCodeForm


@require_POST
def guest_login_view(request):
    """Creates a guest user and logs them in."""
    username = generate_username(1)[0]
    user = User.objects.create_user(
        username=f"{username}",
        email=f"{username}@anon.cosound.io",
        password=None,
    )

    if not hasattr(user, "voter"):
        Voter.objects.create(user=user)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    if request.headers.get("HX-Request"):
        return HttpResponse(status=204, headers={"HX-Trigger": "authSuccess"})

    return redirect(request.GET.get("next", "/"))


def htmx_auth_options(request):
    """Render the initial modal options."""
    return render(request, "account/partials/auth_options.html")


def htmx_login_email(request):
    """
    Step 1: Validate email (auto-signup if new), generate code, and send it.
    """
    form = UnifiedRequestLoginCodeForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        adapter = get_adapter(request)

        # Generate & Send Code
        code = adapter.generate_login_code()
        adapter.send_mail("account/email/login_code", email, {"code": code})

        # Store simple state in session (don't use set_expiry - it affects entire session!)
        request.session["login_code"] = code
        request.session["login_email"] = email

        return render(request, "account/partials/login_code.html", {"email": email})

    return render(request, "account/partials/login_email.html", {"form": form})


def htmx_login_code(request):
    """
    Step 2: Verify code and login.
    """
    email = request.session.get("login_email")
    correct_code = request.session.get("login_code")

    if not email or not correct_code:
        # Session expired or invalid flow -> Reset to start
        return render(request, "account/partials/auth_options.html")

    error = None
    if request.method == "POST":
        input_code = request.POST.get("code", "").strip()

        if input_code == correct_code:
            try:
                user = User.objects.get(email__iexact=email)
                login(
                    request, user, backend="django.contrib.auth.backends.ModelBackend"
                )

                # Cleanup
                del request.session["login_code"]
                del request.session["login_email"]

                return HttpResponse(status=204, headers={"HX-Trigger": "authSuccess"})
            except User.DoesNotExist:
                error = "User not found."
        else:
            error = "Invalid code."

    return render(
        request,
        "account/partials/login_code.html",
        {"email": email, "error": error, "value": request.POST.get("code", "")},
    )


def extract_sound_ids(cosound):
    sound_ids = []
    if cosound and getattr(cosound, "layers", None):
        for layer in cosound.layers:
            sound_id = getattr(layer, "sound_id", None)
            if sound_id:
                sound_ids.append(sound_id)
    return sound_ids


def voting_view(request):
    # Get URL parameters
    player_token = request.GET.get("player_token")
    choice = request.GET.get("choice")

    # Validate parameters
    if not player_token or choice is None:
        return HttpResponse(
            "Missing required parameters: player_token and choice", status=400
        )

    # Convert choice to vote value (1 or -1)
    is_upvote = choice.lower() in ["true", "1", "yes"]
    vote_value = 1 if is_upvote else -1

    # Get the player object
    player = get_object_or_404(Player, token=player_token)

    # Check if user is logged in
    if not request.user.is_authenticated:
        return render(
            request,
            "voter/voting/index.html",
            {
                "requires_login": True,
                "player": player,
            },
        )

    # Get voter card data
    voter_profile, _ = Voter.objects.get_or_create(user=request.user)
    voter_vote_count = Vote.objects.filter(voter=voter_profile).count()
    voter_data = {
        "num_votes": voter_vote_count,
        "join_date": request.user.date_joined.strftime("%b %Y"),
        "username": request.user.username,
        "user_id": request.user.id,
    }

    # User is logged in, check rate limiting (60 seconds)
    one_minute_ago = timezone.now() - timedelta(seconds=60)
    recent_vote = Vote.objects.filter(
        voter=voter_profile, player=player, created_at__gte=one_minute_ago
    ).first()

    if recent_vote:
        # Build layers for rate-limited view
        cosound = player.playing
        layers = []
        if cosound:
            sound_ids = extract_sound_ids(cosound)
            sounds = Sound.objects.filter(id__in=sound_ids) if sound_ids else []
            sounds_dict = {str(sound.pk): sound for sound in sounds}
            layer_index = 1

            for layer in cosound.layers:
                sound_id = getattr(layer, "sound_id", None)
                sound = sounds_dict.get(str(sound_id)) if sound_id else None
                sound_type = getattr(layer, "sound_type", None) or getattr(
                    layer, "type", "Layer"
                )
                gain_value = getattr(layer, "sound_gain", 0.5) or 0.5
                layers.append(
                    {
                        "id": f"item{layer_index}",
                        "layer_type": f"{sound_type} Layer",
                        "gain_level": f"{gain_value:.2f}",
                        "sound_name": (
                            sound.title
                            if sound
                            else getattr(layer, "sound_title", "Unknown Sound")
                        ),
                        "recording_artist": (
                            sound.artist
                            if sound
                            else getattr(layer, "sound_artist", "Unknown Artist")
                        ),
                        "artwork_url": f"https://picsum.photos/seed/{sound_id}/400/400",
                    }
                )
                layer_index += 1

        return render(
            request,
            "voter/voting/index.html",
            {
                "rate_limited": True,
                "player": player,
                "client": player.account.manager,
                "recent_vote": recent_vote,
                "last_vote_timestamp": recent_vote.created_at,
                "layers": layers,
                "voter_data": voter_data,
            },
        )

    # Get the cosound from the player's SchemaField
    cosound = player.playing

    if not cosound:
        return HttpResponse("No cosound available for this player", status=404)

    # Create the vote
    voter_obj = voter_profile if not request.user.is_anonymous else None

    vote = Vote.objects.create(
        value=vote_value,
        voter=voter_profile,
        player=player,
        cosound=cosound,
    )

    # Get Sound objects from cosound JSON and build layer data
    sound_ids = extract_sound_ids(cosound)
    sounds = Sound.objects.filter(id__in=sound_ids) if sound_ids else []
    sounds_dict = {str(sound.pk): sound for sound in sounds}

    # Build enriched layer data for cotton components
    layers = []
    layer_index = 1

    for layer in cosound.layers:
        sound_id = getattr(layer, "sound_id", None)
        sound = sounds_dict.get(str(sound_id)) if sound_id else None
        sound_type = getattr(layer, "sound_type", None) or getattr(
            layer, "type", "Layer"
        )
        gain_value = getattr(layer, "sound_gain", 0.5) or 0.5
        layers.append(
            {
                "id": f"item{layer_index}",
                "layer_type": f"{sound_type} Layer",
                "gain_level": f"{gain_value:.2f}",
                "sound_name": (
                    sound.title
                    if sound
                    else getattr(layer, "sound_title", "Unknown Sound")
                ),
                "recording_artist": (
                    sound.artist
                    if sound
                    else getattr(layer, "sound_artist", "Unknown Artist")
                ),
                "artwork_url": f"https://picsum.photos/seed/{sound_id}/400/400",
            }
        )
        layer_index += 1

    # Render the voting view with all context
    return render(
        request,
        "voter/voting/index.html",
        {
            "vote": vote,
            "player": player,
            "client": player.account.manager,
            "voter": voter_obj,
            "sounds": sounds,
            "layers": layers,
            "success": True,
            "voter_data": voter_data,
        },
    )
