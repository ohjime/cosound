import json
import requests
from rich.console import Console
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
import typer
import sys
import os
import shutil
import string, secrets
from pathlib import Path
from typing import cast
from datetime import datetime, timezone
from dotenv import load_dotenv
import time

import typer
import pygame
import random
import requests
import questionary

from app.utils import delete_last_lines

BASE_DIR = Path(__file__).resolve().parents[4]
# Load project .env when running from source; this may be missing in packaged builds.
load_dotenv(BASE_DIR / "env" / ".env")

# Default to production mode when no DEBUG is provided so packaged apps
# talk to the live API instead of localhost.
DEBUG = os.getenv("DEBUG", "False") == "True"
CHARS = string.ascii_uppercase + string.digits

DEFAULT_DEV_API = "http://localhost:8000/api"
DEFAULT_PROD_API = "https://cosound-server.onrender.com/api"

if DEBUG:
    API_URL = cast(str, os.getenv("DEV_API_URL", DEFAULT_DEV_API))
else:
    API_URL = cast(str, os.getenv("PROD_API_URL", DEFAULT_PROD_API))

BASE_DIR = Path(__file__).resolve().parents[3]
MEDIA_PATH = Path(__file__).parent.parent.parent / "media"
MANIFEST_PATH = Path(__file__).parent.parent.parent / "manifest.json"

console = Console()


def login_and_get_tokens():
    AUTHENTICATED = False
    print("Auhenticated Required.\n")
    while not AUTHENTICATED:
        try:
            email = typer.prompt(typer.style("Email", bold=True))
            password = typer.prompt(typer.style("Password", bold=True), hide_input=True)
            print()
            with console.status(
                f"[bold blue]Authenticating...[/bold blue]", spinner="dots"
            ):
                resp = requests.get(  # Gets list of clients for this user
                    f"{API_URL.rstrip('/')}/core/client/list",
                    auth=(email, password),
                    timeout=15,
                )
            resp.raise_for_status()  # Raises error if status is not 200 OK
            AUTHENTICATED = True
        except Exception as e:
            delete_last_lines(5)
            typer.secho(
                "... Try Again 😡\n",
                fg=typer.colors.RED,
                bold=False,
            )
    delete_last_lines(5)
    typer.secho("Authenticated! 😊\n", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"Welcome, {email}\n")  # type: ignore
    clients = {client["name"]: client["token"] for client in resp.json()}  # type: ignore
    if clients == {}:
        typer.echo("No clients found for this user.")
        raise typer.Exit(code=1)
    selected_client = questionary.select(
        "Select a Client Account",
        choices=clients.keys(),  # type: ignore
    ).ask()
    client_token = clients[selected_client]
    with console.status(f"[bold blue]Fetching Players...[/bold blue]", spinner="dots"):
        resp = requests.get(  # Gets list of players for this client
            f"{API_URL.rstrip('/')}/core/player/list",
            headers={"X-API-Key": client_token},
            timeout=15,
        )
    resp.raise_for_status()
    players = {player["name"]: player["token"] for player in resp.json()}
    if players == {}:
        typer.echo("No players found for this client.")
        raise typer.Exit(code=1)
    selected_player = questionary.select(
        f"Select an available Player",
        choices=players.keys(),  # type: ignore
    ).ask()
    player_token = players[selected_player]

    return client_token, player_token


def download_sound(sound: dict, client_token: str):

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)
    remote_id = str(sound.get("id"))
    remote_timestamp = datetime.fromisoformat(sound["timestamp"])
    try:
        local_sound = manifest[remote_id]
        local_timestamp = datetime.fromisoformat(local_sound["timestamp"])
    except KeyError:
        local_timestamp = datetime.fromtimestamp(0, tz=timezone.utc)
    if remote_timestamp > local_timestamp:
        remote_path = sound["audio"]
        filename = "".join(secrets.choice(CHARS) for _ in range(14))
        local_path = os.path.join(MEDIA_PATH, filename)
        sound_resp = requests.get(  # Download file from cloud storage
            url=remote_path,
            headers={"X-API-Key": client_token},
            timeout=30,
        )
        sound_resp.raise_for_status()  # Raise Exception if not HTTP 200
        os.makedirs(MEDIA_PATH, exist_ok=True)

        # Save original file temporarily
        temp_path = local_path + "_temp"
        with open(temp_path, "wb") as f:
            f.write(sound_resp.content)

        # Convert to MP3 using ffmpeg for pygame compatibility
        import subprocess

        final_path = local_path + ".mp3"
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    temp_path,
                    "-acodec",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    final_path,
                ],
                check=True,
                capture_output=True,
            )
            os.remove(temp_path)  # Remove temp file after conversion
            local_path = final_path
        except (subprocess.CalledProcessError, FileNotFoundError):
            # ffmpeg not available or failed, use original file
            os.rename(temp_path, local_path)

        local_path = os.path.abspath(local_path)
        manifest[remote_id] = {
            "path": local_path,
            "timestamp": remote_timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        with open(MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=2)


def get_library(client_token: str, player_token: str):

    os.remove(MANIFEST_PATH) if os.path.exists(MANIFEST_PATH) else None
    with open(MANIFEST_PATH, "w") as f:
        manifest = {}
        json.dump(manifest, f)

    library_resp = requests.get(  # Gets all library sounds for this player
        f"{API_URL.rstrip('/')}/core/player/library?player={player_token}",
        headers={"X-API-Key": client_token},
        timeout=15,
    )
    library_resp.raise_for_status()
    with console.status(
        f"[bold cyan]Downloading Sound Library...[/bold cyan]", spinner="dots"
    ):
        for sound in library_resp.json():
            download_sound(sound, client_token)
    typer.secho("\nLibrary Downloaded Locally! ✅\n", fg=typer.colors.GREEN, bold=True)


def check_media() -> bool:
    """Check if the media folder exists and contains files."""
    if not MEDIA_PATH.exists():
        return False
    # Check for any files (not directories) in the media folder
    files = [f for f in MEDIA_PATH.iterdir() if f.is_file()]
    return len(files) > 0


def get_cosound(client_token: str, player_token: str):

    cosound_resp = requests.get(
        f"{API_URL.rstrip('/')}/core/cosound?player={player_token}",
        headers={"X-API-Key": client_token},
        timeout=15,
    )
    cosound_resp.raise_for_status()
    cosound_data = cosound_resp.json()

    # Download soundscapes
    soundscapes_with_gain = []
    for soundscape in cosound_data.get("soundscapes", []):
        download_sound(soundscape, client_token)
        soundscapes_with_gain.append(
            {
                "id": soundscape["id"],
                "gain": soundscape.get("gain", {"global": 1.0}),
            }
        )

    # Download instrumentals
    instrumentals_with_gain = []
    for instrumental in cosound_data.get("instrumental", []):
        download_sound(instrumental, client_token)
        instrumentals_with_gain.append(
            {
                "id": instrumental["id"],
                "gain": instrumental.get("gain", {"global": 1.0}),
            }
        )

    return {
        "soundscapes": soundscapes_with_gain,
        "instrumental": instrumentals_with_gain,
        "timestamp": cosound_data.get("timestamp"),
    }
