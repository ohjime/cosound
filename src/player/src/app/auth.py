"""Authentication module for headless/GUI login."""

import os
import requests
from pathlib import Path
from dotenv import load_dotenv
from typing import cast

BASE_DIR = Path(__file__).resolve().parents[4]
# Load project .env when running from source; this may be missing in packaged builds.
load_dotenv(BASE_DIR / "env" / ".env")

# Default to production mode when no DEBUG is provided so packaged apps
# talk to the live API instead of localhost.
DEBUG = os.getenv("DEBUG", "False") == "True"

DEFAULT_DEV_API = "http://localhost:8000/api"
DEFAULT_PROD_API = "https://cosound-server.onrender.com/api"

if DEBUG:
    API_URL = cast(str, os.getenv("DEV_API_URL", DEFAULT_DEV_API))
else:
    API_URL = cast(str, os.getenv("PROD_API_URL", DEFAULT_PROD_API))


def authenticate(email: str, password: str) -> dict[str, str] | None:
    """
    Authenticate and return dict of clients {name: token}.
    Returns None if authentication fails.
    """
    try:
        resp = requests.get(
            f"{API_URL.rstrip('/')}/core/client/list",
            auth=(email, password),
            timeout=15,
        )
        resp.raise_for_status()
        clients = resp.json()
        if not clients:
            return None
        return {client["name"]: client["token"] for client in clients}
    except Exception:
        return None


def get_players(client_token: str) -> dict[str, str] | None:
    """
    Get players for a client. Returns dict {name: token}.
    Returns None if request fails.
    """
    try:
        resp = requests.get(
            f"{API_URL.rstrip('/')}/core/player/list",
            headers={"X-API-Key": client_token},
            timeout=15,
        )
        resp.raise_for_status()
        players = resp.json()
        if not players:
            return None
        return {player["name"]: player["token"] for player in players}
    except Exception:
        return None


def login_and_select_player(email: str, password: str) -> tuple[str, str] | None:
    """
    Authenticate and return (client_token, player_token).
    Returns None if authentication fails.
    Uses first available client and player automatically.
    """
    try:
        # Authenticate and get clients
        resp = requests.get(
            f"{API_URL.rstrip('/')}/core/client/list",
            auth=(email, password),
            timeout=15,
        )
        resp.raise_for_status()
        clients = resp.json()

        if not clients:
            return None

        # Use first client
        client_token = clients[0]["token"]

        # Get players for this client
        resp = requests.get(
            f"{API_URL.rstrip('/')}/core/player/list",
            headers={"X-API-Key": client_token},
            timeout=15,
        )
        resp.raise_for_status()
        players = resp.json()

        if not players:
            return None

        # Use first player
        player_token = players[0]["token"]

        return client_token, player_token

    except Exception:
        return None
