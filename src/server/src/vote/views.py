import json

from django.http import HttpResponse
from django.shortcuts import render

from core.models import Cosound, Listener
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
    Vote.objects.create(
        voter=listener,
        player=player,
        cosound=cosound,
        value=value,
        section=context.get("section") or "",
    )

    if value == 1 and layers:
        listener.collection.add(*[sound_id for sound_id, _ in layers])

    response = HttpResponse("")
    response["HX-Trigger"] = json.dumps(
        {"vote-success": {"voters": serialize_recent_votes(player)}}
    )
    return response
