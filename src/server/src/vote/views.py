import json

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from core.models import Cosound, Listener
from core.prediction import Mix, MixLayer
from core.utils import add_card
from vote.models import Vote
from vote.utils import build_vote_context, get_throttle_seconds_left, serialize_recent_votes


def voter_index(request):
    return render(request, "vote/index.html")


def vote_initial(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(request, "vote/index.html#initial", build_vote_context(request))


def submit_vote(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    context = build_vote_context(request)
    player = context["player"]
    choice = context["choice"]

    if player is None or choice is None:
        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps(
            {"vote-throttled": {"seconds_left": 60}}
        )
        return response

    if not request.user.is_authenticated:
        request.session["post_login_partial"] = "vote/index.html#post_login"
        response = add_card(
            target_deck="deck",
            template="login/index.html#card",
            request=request,
            context={"allow_anonymous": True},
        )
        response["HX-Trigger"] = "auth-required"
        return response

    listener, _ = Listener.objects.get_or_create(user=request.user)
    seconds_left = get_throttle_seconds_left(listener)
    if seconds_left > 0:
        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps(
            {"vote-throttled": {"seconds_left": seconds_left}}
        )
        return response

    layers = [(layer.sound_id, layer.sound_gain) for layer in player.playing.layers]
    cosound = Cosound.get_or_create_from_layers(layers)
    value = int(choice)
    exposure = player.current_exposure
    if exposure is not None:
        try:
            playing_mix_key = Mix(
                tuple(
                    MixLayer(layer.sound_id, layer.sound_gain)
                    for layer in player.playing.layers
                    if layer.sound_gain > 0
                )
            ).key
        except ValueError:
            playing_mix_key = None
        if (
            exposure.player_id != player.pk
            or exposure.ended_at is not None
            or exposure.mix_key != playing_mix_key
        ):
            exposure = None
    attribution_quality = Vote.UNATTRIBUTED
    if exposure is not None:
        if exposure.acknowledged_at is None:
            attribution_quality = Vote.SERVER_CURRENT
        elif (
            exposure.estimated_audible_at is not None
            and timezone.now() < exposure.estimated_audible_at
        ):
            attribution_quality = Vote.TRANSITION_UNCERTAIN
        else:
            attribution_quality = Vote.PLAYER_ACKNOWLEDGED
    Vote.objects.create(
        voter=listener,
        player=player,
        cosound=cosound,
        value=value,
        section=context.get("section") or "",
        exposure=exposure,
        attribution_quality=attribution_quality,
    )

    response = HttpResponse("")
    response["HX-Trigger"] = json.dumps(
        {"vote-success": {"voters": serialize_recent_votes(player)}}
    )
    return response
