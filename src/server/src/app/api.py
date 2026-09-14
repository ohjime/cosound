from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.security import APIKeyHeader
from ninja.throttling import AuthRateThrottle
from pydantic import Field

from core.models import PlaybackExposure, Player, Sound

api = NinjaAPI()


class PlayerTokenAuth(APIKeyHeader):
    param_name = "X-API-Key"

    def authenticate(self, request, key):
        try:
            return Player.objects.get(token=key)
        except Player.DoesNotExist:
            return None


class ExposureAcknowledgement(Schema):
    transition_seconds: float = Field(default=10.0, ge=0.0, le=300.0)


@api.get(
    "/manifest",
    auth=PlayerTokenAuth(),
    throttle=[AuthRateThrottle("10/m")],
)
def get_manifest(request) -> dict[str, str]:
    """Return the player's sound library as {sound_id: remote_url}."""
    player: Player = request.auth
    return {
        str(sound.pk): request.build_absolute_uri(sound.file.url)
        for sound in player.sounds.all()
        if sound.file
    }


@api.get(
    "/cosound",
    auth=PlayerTokenAuth(),
    throttle=[AuthRateThrottle("10/m")],
)
def get_cosound(request) -> dict[str, float]:
    """Return the player's latest cosound as {sound_id: gain}."""
    player: Player = request.auth
    return {
        str(layer.sound_id): layer.sound_gain
        for layer in player.playing.layers
    }


@api.get(
    "/player",
    auth=PlayerTokenAuth(),
    throttle=[AuthRateThrottle("10/m")],
)
def get_player(request) -> dict:
    """Return player details and the currently playing cosound layers."""
    player: Player = request.auth
    sounds = Sound.objects.in_bulk(
        [layer.sound_id for layer in player.playing.layers]
    )
    exposure = player.current_exposure
    if exposure is not None and exposure.ended_at is not None:
        exposure = None
    return {
        "name": player.name,
        "manager": player.manager.name,
        "location": player.location,
        "decision_id": (
            str(exposure.opening_decision_id) if exposure is not None else None
        ),
        "exposure_id": str(exposure.exposure_id) if exposure is not None else None,
        "layers": [
            {
                "sound_id": layer.sound_id,
                "title": (
                    sounds[layer.sound_id].title
                    if layer.sound_id in sounds
                    else f"Sound {layer.sound_id}"
                ),
                "artist": (
                    sounds[layer.sound_id].artist_name
                    if layer.sound_id in sounds
                    else ""
                ),
                "gain": layer.sound_gain,
            }
            for layer in player.playing.layers
        ],
    }


@api.post(
    "/exposures/{exposure_id}/ack",
    auth=PlayerTokenAuth(),
    throttle=[AuthRateThrottle("30/m")],
)
def acknowledge_exposure(
    request,
    exposure_id: UUID,
    payload: ExposureAcknowledgement,
) -> dict:
    """Record that the authenticated player received and queued an exposure."""
    authenticated_player: Player = request.auth
    with transaction.atomic():
        player = Player.objects.select_for_update().get(pk=authenticated_player.pk)
        if player.current_exposure_id != exposure_id:
            raise HttpError(404, "Active exposure not found")
        exposure = (
            PlaybackExposure.objects.select_for_update()
            .filter(
                exposure_id=exposure_id,
                player=player,
                ended_at__isnull=True,
            )
            .first()
        )
        if exposure is None:
            raise HttpError(404, "Active exposure not found")

        if exposure.acknowledged_at is None:
            acknowledged_at = timezone.now()
            exposure.acknowledged_at = acknowledged_at
            exposure.transition_seconds = payload.transition_seconds
            exposure.estimated_audible_at = acknowledged_at + timedelta(
                seconds=payload.transition_seconds
            )
            exposure.status = PlaybackExposure.PLAYER_ACKNOWLEDGED
            exposure.save(
                update_fields=[
                    "acknowledged_at",
                    "transition_seconds",
                    "estimated_audible_at",
                    "status",
                    "updated_at",
                ]
            )

    return {
        "exposure_id": str(exposure.exposure_id),
        "status": exposure.status,
        "acknowledged_at": (
            exposure.acknowledged_at.isoformat()
            if exposure.acknowledged_at is not None
            else None
        ),
        "estimated_audible_at": (
            exposure.estimated_audible_at.isoformat()
            if exposure.estimated_audible_at is not None
            else None
        ),
    }


# Resolve the NinjaAPI's URLs exactly once. django-ninja refuses to attach the
# same NinjaAPI instance twice (ConfigError on a duplicate namespace), so both
# mount points — "/api/" in config.urls and "/" in config.urls_api (the
# api.cosound.ca subdomain) — must reuse this single tuple.
api_urls = api.urls
