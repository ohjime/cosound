from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render

from core.models import Listener, Sound
from library.utils import serialize_sounds
from studio.utils import get_artist

# The studio's views. The builder is served two ways from the same partials:
# `studio_index` is the standalone page (cosound.ca/studio/ and the root of
# studio.*), and `studio_initial` is the content fragment that page's loader —
# and the home page's STUDIO tab — fetch over htmx.
#
# The mix itself is not server state. Layers live in the browser's `soundLayers`
# Alpine store, and a layer built from a dropped file never leaves the tab, so
# there is nothing here that creates, updates or stores a draft. These views only
# hand over the library the artist can pull from.


def _blank_layer(index=1):
    """One empty layer for the builder to open on.

    The studio never shows an empty canvas — it starts you on a blank layer to
    fill in. Seeding it here rather than from the browser matters: the store
    hands its whole layer list to the engine inside `initialize()`, and a layer
    added from the client before that finishes would be wiped when setLayers
    assigns its freshly prepared voices. Coming in with the page, it is simply
    part of the first load.

    `artwork_url` is left empty on purpose; the store fills in a placeholder
    when it normalises the layer.
    """
    return {
        "sound_id": f"draft-{index}",
        "sound_file": "",
        "sound_title": "",
        # No one owns the void; a new sound is credited when it is created.
        "sound_artist": "",
        "artwork_url": "",
        "gain": 50,
        "mute": False,
        "saved": False,
        "flavor": "In the begining there was darkness.",
        "tags": "Void",
        "is_local": True,
        "is_draft": True,
    }


def _library(user):
    """The sounds this user has collected, as a queryset.

    The studio pulls from the same Listener collection the library's swap panel
    uses — an artist builds with sounds they have kept, not the whole catalogue.
    """
    try:
        return Listener.objects.get(user=user).collection.all()
    except Listener.DoesNotExist:
        from core.models import Sound

        return Sound.objects.none()


def studio_index(request):
    """The standalone studio page; its c-core-loader fetches `studio:initial`."""
    return render(request, "studio/index.html")


def studio_initial(request):
    """The builder content itself, as an htmx fragment.

    Two callers: the standalone page's loader, and the home page's STUDIO tab
    (c-app-navigation-tabs swaps it into #tab_content).
    """
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(
        request,
        "studio/index.html#initial",
        {"seed_layers": [_blank_layer()]},
    )


def studio_library(request):
    """Open the library picker over the card.

    Answers with out-of-band swaps for both card regions, the same shape the
    library's swap panel uses, so one response repaints the figure and the body.
    """
    if not request.htmx:
        return HttpResponse("Request Denied.")
    if get_artist(request.user) is None:
        return HttpResponse("Request Denied.", status=403)

    library = _library(request.user)
    return render(
        request,
        "studio/index.html#library_view",
        {
            "sounds": serialize_sounds(library.order_by("?")[:5]),
            "collection_size": library.count(),
        },
    )


def studio_library_search(request):
    """Filter the picker. An empty query falls back to a random handful."""
    if not request.htmx:
        return HttpResponse("Request Denied.")
    if get_artist(request.user) is None:
        return HttpResponse("Request Denied.", status=403)

    library = _library(request.user)
    query = (request.GET.get("q") or "").strip()
    if query:
        library = library.filter(
            Q(title__icontains=query) | Q(artist__name__icontains=query)
        ).order_by("title")[:20]
    else:
        library = library.order_by("?")[:5]

    return render(
        request,
        "studio/index.html#library_list_items",
        {"sounds": serialize_sounds(library)},
    )


def studio_carousel(request):
    """Close the picker and put the carousel back."""
    if not request.htmx:
        return HttpResponse("Request Denied.")
    return render(request, "studio/index.html#default_view")


# How many existing tags a search in the new-sound panel offers at once. The
# panel is a few lines tall, so a handful of chips is what fits.
TAG_SUGGESTION_LIMIT = 6


def studio_tag_search(request):
    """Existing tags matching what the artist typed into a new sound's tag box.

    A new sound may only carry tags cosound already has, so this is the one way
    a tag gets onto one: only Sound tags are offered, and the panel adds nothing
    that did not come from here. `chosen` (newline-separated) is what the layer
    already carries, left out of the answer. When no tag matches at all, the
    fragment offers to ask cosound to add it instead. `exact` keeps that offer
    away from a tag the layer already carries.
    """
    if not request.htmx:
        return HttpResponse("Request Denied.")
    if get_artist(request.user) is None:
        return HttpResponse("Request Denied.", status=403)

    from django.contrib.contenttypes.models import ContentType
    from taggit.models import Tag

    query = (request.GET.get("q") or "").strip()
    if not query:
        return HttpResponse("")
    chosen = {n.strip().lower() for n in (request.GET.get("chosen") or "").split("\n") if n.strip()}

    sound_tags = Tag.objects.filter(
        taggit_taggeditem_items__content_type=ContentType.objects.get_for_model(Sound)
    ).distinct()
    exact = sound_tags.filter(name__iexact=query).exists()
    names = [
        name
        for name in sound_tags.filter(name__icontains=query)
        .order_by("name")
        .values_list("name", flat=True)
        if name.lower() not in chosen
    ][:TAG_SUGGESTION_LIMIT]

    return render(
        request,
        "studio/index.html#tag_suggestions",
        {"query": query, "tags": names, "exact": exact},
    )
