from typing import List

from django.contrib.auth import authenticate
from ninja import NinjaAPI
from ninja.orm import ModelSchema
from ninja.security import APIKeyHeader, HttpBasicAuth
from ninja.throttling import AuthRateThrottle

from core.models import Player, PlayerAccount, Sound, User


api = NinjaAPI()


class BasicAuth(HttpBasicAuth):
    def authenticate(self, request, username, password):
        return authenticate(
            request,
            username=username,
            password=password,
        )


class PlayerAccountOut(ModelSchema):
    """Output schema for PlayerAccount (was Client in old API)."""

    token: str  # We'll use the pk as a pseudo-token for PlayerAccount

    class Meta:
        model = PlayerAccount
        fields = ["name"]

    @staticmethod
    def resolve_token(obj: PlayerAccount) -> str:
        # Use pk as the identifier since PlayerAccount doesn't have a token field
        return f"account_{obj.pk}"


@api.get(
    "/client/list",
    response=List[PlayerAccountOut],
    auth=BasicAuth(),
    throttle=[AuthRateThrottle("10/m")],
)
def get_clients(request):
    """Get all PlayerAccounts (clients) for the authenticated user."""
    user: User = request.auth
    return PlayerAccount.objects.filter(manager=user)


class PlayerAccountTokenAuth(APIKeyHeader):
    """Auth using PlayerAccount pseudo-token (account_{pk})."""

    param_name = "X-API-Key"

    def authenticate(self, request, key):
        # Check if it's a PlayerAccount pseudo-token
        if key.startswith("account_"):
            try:
                pk = int(key.replace("account_", ""))
                return {"type": "account", "obj": PlayerAccount.objects.get(pk=pk)}
            except (ValueError, PlayerAccount.DoesNotExist):
                return None
        # Otherwise, treat as a Player token
        try:
            return {"type": "player", "obj": Player.objects.get(token=key)}
        except Player.DoesNotExist:
            return None


class PlayerOut(ModelSchema):
    class Meta:
        model = Player
        fields = ["name", "token"]


@api.get(
    "/player/list",
    response=List[PlayerOut],
    auth=PlayerAccountTokenAuth(),
    throttle=[AuthRateThrottle("10/m")],
)
def get_players(request):
    """Get all Players for the authenticated PlayerAccount."""
    auth_info = request.auth
    if auth_info["type"] != "account":
        return api.create_response(
            request,
            {"detail": "Invalid authentication. Use PlayerAccount token."},
            status=401,
        )
    account: PlayerAccount = auth_info["obj"]
    return Player.objects.filter(account=account)


class SoundOut(ModelSchema):
    """Output schema for Sound in library listing."""

    audio: str  # Map 'file' to 'audio' for client compatibility
    timestamp: str  # Map 'created_at' to 'timestamp'

    class Meta:
        model = Sound
        fields = ["id", "type"]

    @staticmethod
    def resolve_audio(obj: Sound) -> str:
        return obj.file.url

    @staticmethod
    def resolve_timestamp(obj: Sound) -> str:
        return obj.created_at.isoformat()


class PlayerTokenAuth(APIKeyHeader):
    """Auth using Player token directly."""

    param_name = "X-API-Key"

    def authenticate(self, request, key):
        # Check if it's a PlayerAccount pseudo-token (for backwards compat)
        if key.startswith("account_"):
            try:
                pk = int(key.replace("account_", ""))
                return {"type": "account", "obj": PlayerAccount.objects.get(pk=pk)}
            except (ValueError, PlayerAccount.DoesNotExist):
                return None
        # Otherwise, treat as a Player token
        try:
            return {"type": "player", "obj": Player.objects.get(token=key)}
        except Player.DoesNotExist:
            return None


@api.get(
    "/player/library",
    response=List[SoundOut],
    auth=PlayerTokenAuth(),
    throttle=[AuthRateThrottle("10/m")],
)
def get_player_library(request, player: str):
    """Get all sounds in a player's library."""
    auth_info = request.auth

    # Get the PlayerAccount for authorization
    if auth_info["type"] == "account":
        account: PlayerAccount = auth_info["obj"]
    else:
        # Player token provided, get the account from the player
        player_obj: Player = auth_info["obj"]
        account = player_obj.account

    try:
        player_obj = Player.objects.get(token=player, account=account)
    except Player.DoesNotExist:
        return api.create_response(
            request,
            {"detail": "Player not found."},
            status=404,
        )

    return player_obj.library.all()


@api.get(
    "/cosound",
    auth=PlayerTokenAuth(),
    throttle=[AuthRateThrottle("10/m")],
)
def get_cosound(request, player: str):
    """Get the current cosound configuration for a player."""
    auth_info = request.auth

    # Get the PlayerAccount for authorization
    if auth_info["type"] == "account":
        account: PlayerAccount = auth_info["obj"]
    else:
        # Player token provided, get the account from the player
        player_obj: Player = auth_info["obj"]
        account = player_obj.account

    try:
        player_obj = Player.objects.get(token=player, account=account)
        cosound = player_obj.playing  # Cosound Pydantic model

        # Build response in format the client expects
        # Old API had separate 'soundscapes' and 'instrumental' lists
        # New model has unified 'layers' list with 'sound_type' field
        soundscapes = []
        instrumentals = []

        for layer in cosound.layers:
            try:
                sound = Sound.objects.get(id=layer.sound_id)
                sound_data = {
                    "id": sound.pk,
                    "audio": sound.file.url,
                    "title": sound.title,
                    "artist": sound.artist,
                    "type": sound.type,
                    "timestamp": sound.created_at.isoformat(),
                    "gain": {"global": layer.sound_gain},  # Client expects dict format
                }
                # Categorize based on sound type
                if layer.sound_type == "Soundscape":
                    soundscapes.append(sound_data)
                else:  # Instrumental or any other type
                    instrumentals.append(sound_data)
            except Sound.DoesNotExist:
                continue

        return {
            "soundscapes": soundscapes,
            "instrumental": instrumentals,
            "timestamp": cosound.created_at.isoformat() if cosound.created_at else None,
        }

    except Player.DoesNotExist:
        return api.create_response(
            request,
            {"detail": "Player not found."},
            status=404,
        )
