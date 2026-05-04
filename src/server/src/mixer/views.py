import json

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from core.models import Cosound, Listener, Sound
from core.utils import add_card, close_modal, show_modal
from app.utils import serialize_mix
from mixer.models import SoundMix
from mixer.utils import get_random_sounds, parse_layers, serialize_sounds


def mixer_index(request):
    if request.htmx:
        sounds = get_random_sounds(user=request.user)
        return add_card(
            target_deck="deck",
            template="mixer/index.html#mixer",
            request=request,
            context={"sounds": sounds},
        )
    return HttpResponse("Mixer index page.")


def mixer_save(request):

    if not request.htmx:
        return HttpResponse("Request Denied.")

    if not request.user.is_authenticated:
        response = add_card(
            target_deck="deck",
            template="login/index.html#card",
            request=request,
        )
        response["HX-Trigger"] = "auth-required"
        return response

    layer_data, layers = parse_layers(request.POST.get("layers"))
    if layer_data is None:
        return HttpResponse("Invalid data.", status=400)
    if not layers:
        return HttpResponse("No layers provided.", status=400)

    hashid = Cosound.compute_hashid(layers)
    existing = SoundMix.objects.filter(
        creator=request.user, cosound__hashid=hashid
    ).first()

    return show_modal(
        request,
        "app/home.html#mix_title_modal",
        {
            "layers_json": json.dumps(layer_data),
            "existing_title": existing.title if existing else "",
        },
    )


def mixer_save_confirm(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    if not request.user.is_authenticated:
        return HttpResponse("Request Denied.", status=401)

    _, layers = parse_layers(request.POST.get("layers"))
    if not layers:
        return HttpResponse("No layers provided.", status=400)

    title = (request.POST.get("title") or "").strip()

    cosound = Cosound.get_or_create_from_layers(layers)
    sound_mix, created = SoundMix.objects.get_or_create(
        creator=request.user, cosound=cosound
    )
    sound_mix.title = title
    sound_mix.save(update_fields=["title", "updated_at"])

    if not created:
        return close_modal(request)

    response = close_modal(request)
    response["HX-Trigger"] = json.dumps(
        {
            "close-modal": True,
            "mix-saved": {"mix": serialize_mix(sound_mix)},
        }
    )
    return response


def mixer_keep_sound(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    if not request.user.is_authenticated:
        return add_card(
            target_deck="deck",
            template="login/index.html#card",
            request=request,
        )

    sound_id = request.POST.get("sound_id")
    try:
        sound = Sound.objects.get(pk=sound_id)
    except Sound.DoesNotExist:
        return HttpResponse("Sound not found.", status=404)

    listener, _ = Listener.objects.get_or_create(user=request.user)
    if listener.collection.filter(pk=sound.pk).exists():
        listener.collection.remove(sound)
        saved = False
    else:
        listener.collection.add(sound)
        saved = True

    response = HttpResponse("")
    response["HX-Reswap"] = "none"
    response["HX-Trigger"] = json.dumps(
        {"layer-saved": {"saved": saved, "soundId": sound_id}}
    )
    return response


def mixer_swap(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    if not request.user.is_authenticated:
        return HttpResponse("Request Denied.", status=401)

    try:
        listener = Listener.objects.get(user=request.user)
        qs = listener.collection.all()
    except Listener.DoesNotExist:
        qs = Sound.objects.none()

    collection_size = qs.count()
    sounds = serialize_sounds(qs.order_by("?")[:5])
    return render(
        request,
        "mixer/index.html#swap_view",
        {"sounds": sounds, "collection_size": collection_size},
    )


def mixer_search(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")

    if not request.user.is_authenticated:
        return HttpResponse("Request Denied.", status=401)

    try:
        listener = Listener.objects.get(user=request.user)
        qs = listener.collection.all()
    except Listener.DoesNotExist:
        qs = Sound.objects.none()

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(artist__icontains=q)).order_by(
            "title"
        )[:20]
    else:
        qs = qs.order_by("?")[:5]
    return render(
        request,
        "mixer/index.html#swap_list_items",
        {"sounds": serialize_sounds(qs)},
    )


def mixer_carousel(request):
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(request, "mixer/index.html#default_view")
