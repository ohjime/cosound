from ninja import NinjaAPI
from ninja.security import APIKeyHeader
from ninja.throttling import AuthRateThrottle

from core.models import Player, Sound

api = NinjaAPI()


class PlayerTokenAuth(APIKeyHeader):
    param_name = "X-API-Key"

    def authenticate(self, request, key):
        try:
            return Player.objects.get(token=key)
        except Player.DoesNotExist:
            return None


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
