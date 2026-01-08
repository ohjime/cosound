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
load_dotenv(BASE_DIR / ".env" / ".env")
DEBUG = os.getenv("DEBUG", "True") == "True"
CHARS = string.ascii_uppercase + string.digits
BASE_DIR = Path(__file__).resolve().parents[3]
API_URL = cast(str, os.getenv("DEV_API_URL") if DEBUG else os.getenv("PROD_API_URL"))
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
                    f"{API_URL.rstrip('/')}/client/list",
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
            f"{API_URL.rstrip('/')}/player/list",
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
        with open(local_path, "wb") as f:
            f.write(sound_resp.content)
        local_path = os.path.abspath(local_path)
        manifest[remote_id] = {
            "path": local_path,
            "timestamp": remote_timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        with open(MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=2)


def get_library(client_token: str, player_token: str):

    shutil.rmtree(MEDIA_PATH) if os.path.isdir(MEDIA_PATH) else None
    os.remove(MANIFEST_PATH) if os.path.exists(MANIFEST_PATH) else None
    with open(MANIFEST_PATH, "w") as f:
        manifest = {}
        json.dump(manifest, f)

    library_resp = requests.get(  # Gets all library sounds for this player
        f"{API_URL.rstrip('/')}/player/library?player={player_token}",
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


def get_cosound(client_token: str, player_token: str):

    cosound_resp = requests.get(
        f"{API_URL.rstrip('/')}/cosound?player={player_token}",
        headers={"X-API-Key": client_token},
        timeout=15,
    )
    cosound_resp.raise_for_status()
    for sound in cosound_resp.json()["sounds"]:
        download_sound(sound, client_token)

    return cosound_resp.json()["gain"]
