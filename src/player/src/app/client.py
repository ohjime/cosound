import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import wget

ROOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
CONFIG_PATH = os.path.join(ROOT_DIR, "cosound.json")
PLAY_SCRIPT = os.path.join(ROOT_DIR, "bin/play")
REFRESH_INTERVAL = 120  # In Seconds
CROSSFADE_INTERVAL = 10  # In Seconds
TMP_STREAM_DIR = "/tmp/cosound"
VOTE_CHIME_CACHE_DIR = os.path.join(ROOT_DIR, "vote_chimes")
VOTE_CHIME_DOWNLOAD_LIMIT = 5 * 1024 * 1024
VOTE_CHIME_CACHE_LIMIT = 8

API_BASE_URL = (
    os.environ.get("COSOUND_API_URL", "http://localhost:8000/api").strip().rstrip("/")
)
HTTP_TIMEOUT = 15  # Bound a failed request so later refreshes can still run.


def _api_get(path: str, api_key: str) -> dict:
    request = urllib.request.Request(
        f"{API_BASE_URL}{path}",
        headers={"X-API-Key": api_key},
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def get_latest_manifest(api_key: str) -> dict:
    """Fetch the player's sound library: {sound_id: remote_url}."""
    return _api_get("/manifest", api_key)


def get_latest_cosound(api_key: str) -> dict:
    """Fetch the player's latest cosound: {sound_id: gain}."""
    return _api_get("/cosound", api_key)


def get_player_info(api_key: str) -> dict:
    """Fetch player details and currently playing layers from /player.

    Returns {name, manager, location, layers: [{sound_id, title, artist, gain}]}.
    Falls back to /cosound if the server does not expose /player yet.
    """
    try:
        return _api_get("/player", api_key)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        cosound = get_latest_cosound(api_key)
        return {
            "name": "",
            "manager": "",
            "location": "",
            "layers": [
                {
                    "sound_id": int(sound_id),
                    "title": f"Sound {sound_id}",
                    "artist": "",
                    "gain": gain,
                }
                for sound_id, gain in cosound.items()
            ],
        }


def get_sound(sound_id, remote_path) -> str:
    # First check if sound_id exists locally:
    os.makedirs(ASSETS_DIR, exist_ok=True)
    local_path = os.path.join(ASSETS_DIR, str(sound_id))
    # Otherwise download from remote url to local path
    if not os.path.exists(local_path):
        wget.download(remote_path, local_path)
    return local_path


def get_vote_chime(version: str, remote_path: str) -> str:
    """Return a locally cached vote chime, downloading it atomically if needed.

    ``version`` is the server's stable content identity.  The URL is deliberately
    not part of the key because object-store signatures may change on every
    response even when the underlying upload has not.
    """
    if not isinstance(version, str) or not version:
        raise ValueError("Vote chime version is required")
    if not isinstance(remote_path, str) or not remote_path:
        raise ValueError("Vote chime URL is required")
    try:
        parsed = urlsplit(remote_path)
        parsed.port
    except ValueError as error:
        raise ValueError("Vote chime URL must use HTTP or HTTPS") from error
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Vote chime URL must use HTTP or HTTPS")

    local_path = _vote_chime_cache_path(version)
    os.makedirs(VOTE_CHIME_CACHE_DIR, exist_ok=True)
    if os.path.isfile(local_path) and os.path.getsize(local_path) > 0:
        return local_path

    cache_key = os.path.basename(local_path)
    request = urllib.request.Request(remote_path)
    temporary_path = None
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except (TypeError, ValueError):
                    declared_size = None
                if (
                    declared_size is not None
                    and declared_size > VOTE_CHIME_DOWNLOAD_LIMIT
                ):
                    raise ValueError("Vote chime download is too large")

            descriptor, temporary_path = tempfile.mkstemp(
                prefix=f".{cache_key}.", dir=VOTE_CHIME_CACHE_DIR
            )
            downloaded = 0
            with os.fdopen(descriptor, "wb") as destination:
                while chunk := response.read(64 * 1024):
                    downloaded += len(chunk)
                    if downloaded > VOTE_CHIME_DOWNLOAD_LIMIT:
                        raise ValueError("Vote chime download is too large")
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
        if downloaded == 0:
            raise ValueError("Vote chime download is empty")
        os.replace(temporary_path, local_path)
        temporary_path = None
        return local_path
    finally:
        if temporary_path is not None:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass


def _vote_chime_cache_path(version: str) -> str:
    """Map an opaque server version to one safe path under the chime cache."""
    if not isinstance(version, str) or not version:
        raise ValueError("Vote chime version is required")
    cache_key = hashlib.sha256(version.encode("utf-8")).hexdigest()
    return os.path.join(VOTE_CHIME_CACHE_DIR, cache_key)


def discard_vote_chime(version: str) -> None:
    """Remove one failed cached version without accepting an arbitrary path."""
    try:
        os.remove(_vote_chime_cache_path(version))
    except FileNotFoundError:
        pass


def prune_vote_chimes(keep_version: str | None = None) -> None:
    """Keep a bounded cache without evicting this process's active version."""
    keep_name = (
        os.path.basename(_vote_chime_cache_path(keep_version))
        if keep_version is not None
        else None
    )
    try:
        entries = os.scandir(VOTE_CHIME_CACHE_DIR)
    except OSError:
        return
    with entries:
        cached = []
        for entry in entries:
            is_cache_key = len(entry.name) == 64 and all(
                character in "0123456789abcdef" for character in entry.name
            )
            if not is_cache_key or not entry.is_file(follow_symlinks=False):
                continue
            try:
                modified_at = entry.stat(follow_symlinks=False).st_mtime_ns
            except OSError:
                continue
            cached.append((modified_at, entry))

    cached.sort(key=lambda item: item[0], reverse=True)
    keep_names = {entry.name for _, entry in cached[:VOTE_CHIME_CACHE_LIMIT]}
    if keep_name is not None:
        keep_names.add(keep_name)
        if len(keep_names) > VOTE_CHIME_CACHE_LIMIT:
            for _, entry in reversed(cached):
                if entry.name != keep_name and entry.name in keep_names:
                    keep_names.remove(entry.name)
                    break
    for _, entry in cached:
        if entry.name in keep_names:
            continue
        try:
            os.remove(entry.path)
        except OSError:
            # Cache cleanup must never interrupt live playback or refresh.
            pass
