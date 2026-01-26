import json
from datetime import timedelta

from random_username.generate import generate_username
from allauth.account.adapter import get_adapter
from django.contrib.auth import login
from django.db.models import Max, OuterRef, Subquery
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Player, Sound, User

from voter.models import Favorite, Voter, Vote
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


def build_layer_data(cosound, sounds_dict, favorite_sound_ids):
    layers = []
    layer_index = 1

    for layer in cosound.layers:
        sound_id = getattr(layer, "sound_id", None)
        sound_key = str(sound_id) if sound_id is not None else ""
        sound = sounds_dict.get(sound_key) if sound_key else None
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
                "sound_id": sound_key,
                "liked": sound_key in favorite_sound_ids,
            }
        )
        layer_index += 1

    layers.sort(key=lambda x: (0 if "Instrumental" in x["layer_type"] else 1))
    for i, layer in enumerate(layers, 1):
        layer["id"] = f"item{i}"

    return layers


def get_recent_voters(player, exclude_user=None, limit=5):
    """
    Get the last N distinct voters at this player with their vote data.
    Returns a list of dicts with voter info for the template.
    """
    # Get the most recent vote for each voter at this player
    recent_votes_subquery = (
        Vote.objects.filter(player=player, voter=OuterRef("voter"))
        .order_by("-created_at")
        .values("id")[:1]
    )

    # Get distinct voters with their most recent vote
    recent_votes = (
        Vote.objects.filter(
            player=player,
            id__in=Subquery(
                Vote.objects.filter(player=player)
                .values("voter")
                .annotate(latest_vote_id=Max("id"))
                .values("latest_vote_id")
            ),
        )
        .select_related("voter__user")
        .order_by("-created_at")
    )

    # Exclude the current user if provided
    if exclude_user and not exclude_user.is_anonymous:
        recent_votes = recent_votes.exclude(voter__user=exclude_user)

    recent_votes = recent_votes[:limit]

    voters_data = []
    for vote in recent_votes:
        voter = vote.voter
        user = voter.user

        # Calculate stats for badges
        total_votes = Vote.objects.filter(voter=voter).count()
        votes_here = Vote.objects.filter(voter=voter, player=player).count()

        voters_data.append(
            {
                "username": user.username,
                "user_id": user.pk,
                "avatar_url": f"https://robohash.org/{user.pk}?bgset=bg1&set=set2",
                "vote_value": vote.value,
                "voted_at": vote.created_at,
                "voted_at_iso": vote.created_at.isoformat(),
                "total_votes": total_votes,
                "votes_here": votes_here,
                "join_date_iso": user.date_joined.isoformat(),
            }
        )

    return voters_data


def voting_view(request):
    # Get URL parameters
    player_token = request.GET.get("player_token")
    choice = request.GET.get("choice")
    choice_raw = (choice or "").strip().lower()

    # Validate parameters
    if not player_token or choice is None:
        return HttpResponse(
            "Missing required parameters: player_token and choice", status=400
        )

    # Convert choice to vote value (1 or -1) or mark as refresh (0)
    is_refresh_request = choice_raw in ["0", "", "none", "refresh"]
    is_upvote = choice_raw in ["true", "1", "yes"]
    vote_value = None if is_refresh_request else (1 if is_upvote else -1)

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
    total_votes = Vote.objects.filter(voter=voter_profile).count()
    votes_here = Vote.objects.filter(voter=voter_profile, player=player).count()
    voter_data = {
        "total_votes": total_votes,
        "votes_here": votes_here,
        "join_date": request.user.date_joined.strftime("%b %Y"),
        "join_date_iso": request.user.date_joined.isoformat(),
        "username": request.user.username,
        "user_id": request.user.id,
        "avatar_url": f"https://robohash.org/{request.user.id}?bgset=bg1&set=set2",
    }

    favorite_sound_ids = set(
        str(sound_id)
        for sound_id in Favorite.objects.filter(voter=voter_profile).values_list(
            "sound_id", flat=True
        )
    )
    favorite_url = reverse("voter_toggle_favorite")

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
            layers = build_layer_data(cosound, sounds_dict, favorite_sound_ids)

        # Get recent voters for the "other voters" section
        recent_voters = get_recent_voters(player, exclude_user=request.user, limit=5)

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
                "recent_voters": recent_voters,
                "favorite_url": favorite_url,
            },
        )

    # If this is a refresh request, do not cast a vote; just render the view.
    if is_refresh_request:
        cosound = player.playing

        if not cosound:
            return HttpResponse("No cosound available for this player", status=404)

        sound_ids = extract_sound_ids(cosound)
        sounds = Sound.objects.filter(id__in=sound_ids) if sound_ids else []
        sounds_dict = {str(sound.pk): sound for sound in sounds}
        layers = build_layer_data(cosound, sounds_dict, favorite_sound_ids)

        # Get recent voters for the "other voters" section
        recent_voters = get_recent_voters(player, exclude_user=request.user, limit=5)

        return render(
            request,
            "voter/voting/index.html",
            {
                "ready_to_vote": True,
                "player": player,
                "client": player.account.manager,
                "last_vote_timestamp": recent_vote.created_at if recent_vote else None,
                "layers": layers,
                "voter_data": voter_data,
                "recent_voters": recent_voters,
                "favorite_url": favorite_url,
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
    layers = build_layer_data(cosound, sounds_dict, favorite_sound_ids)

    # Get recent voters for the "other voters" section
    recent_voters = get_recent_voters(player, exclude_user=request.user, limit=5)

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
            "recent_voters": recent_voters,
            "favorite_url": favorite_url,
        },
    )


@require_POST
def toggle_favorite_sound(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        payload = request.POST

    sound_id = payload.get("sound_id") or request.POST.get("sound_id")
    liked_raw = payload.get("liked")

    if isinstance(liked_raw, str):
        liked_value = liked_raw.lower() in ["1", "true", "yes", "on"]
    elif liked_raw is None:
        liked_value = None
    else:
        liked_value = bool(liked_raw)

    if not sound_id:
        return JsonResponse({"detail": "sound_id is required."}, status=400)

    sound = get_object_or_404(Sound, id=sound_id)
    voter, _ = Voter.objects.get_or_create(user=request.user)

    exists = Favorite.objects.filter(voter=voter, sound=sound).exists()
    target_state = liked_value if liked_value is not None else not exists

    if target_state and not exists:
        Favorite.objects.create(voter=voter, sound=sound)
    elif not target_state and exists:
        Favorite.objects.filter(voter=voter, sound=sound).delete()

    return JsonResponse({"liked": target_state})
