"""Authenticated change notifications; HTTP remains the source of player state."""

import asyncio
import json
import os
import random
from collections import deque
from collections.abc import Callable
from time import monotonic
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK, InvalidStatus, WebSocketException

from app.client import API_BASE_URL
from app.sync import ServerClock, finite_number

READY_TIMEOUT = 15
MAX_RETRY_DELAY = 60
STABLE_CONNECTION_SECONDS = 30
INITIAL_CLOCK_PROBES = 8
INITIAL_CLOCK_INTERVAL = 0.15
CLOCK_INTERVAL = 2.0
PROBE_TIMEOUT = 5.0
MAX_PENDING_PROBES = 16


def build_websocket_url(api_url: str, override: str | None = None) -> str:
    """Use the API's origin, not its /api path, for the socket endpoint."""
    explicit = bool(override and override.strip())
    parsed = urlsplit(override.strip() if explicit else api_url.strip())
    schemes = ("ws", "wss") if explicit else ("http", "https")
    if (
        parsed.scheme not in schemes
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Invalid COSOUND_WS_URL or COSOUND_API_URL")
    # Validate the port, including malformed and out-of-range port numbers.
    parsed.port
    if explicit:
        return urlunsplit(parsed)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit((scheme, parsed.netloc, "/ws/player/", "", ""))


class _PlayerConnection(connect):
    def process_redirect(self, exc: Exception) -> Exception:
        # Never forward the custom API-key header to a redirected destination.
        # Configure COSOUND_WS_URL explicitly when a different endpoint is used.
        return exc


def _event(message: str | bytes) -> dict | None:
    try:
        event = json.loads(message)
    except (ValueError, UnicodeDecodeError):
        return None
    if (not isinstance(event, dict) or type(event.get("schema_version")) is not int
            or event["schema_version"] != 1):
        return None
    return event


def _event_type(message: str | bytes) -> str | None:
    event = _event(message)
    return event.get("type") if event is not None else None


async def _clock_messages(websocket, clock: ServerClock, refresh):
    """One socket reader also drives probes; cancellation leaves no timer task."""
    clock.reset()
    pending = {}
    probe_id = 0
    next_probe = monotonic()
    while True:
        now = monotonic()
        if now >= next_probe:
            pending = {key: sent for key, sent in pending.items() if now - sent < PROBE_TIMEOUT}
            if len(pending) >= MAX_PENDING_PROBES:
                pending.pop(next(iter(pending)))
            probe_id += 1
            sent = monotonic()
            pending[probe_id] = sent
            await websocket.send(json.dumps({
                "type": "player.time_ping", "schema_version": 1,
                "id": probe_id, "client_send": sent,
            }))
            next_probe = sent + (INITIAL_CLOCK_INTERVAL if probe_id < INITIAL_CLOCK_PROBES else CLOCK_INTERVAL)
        try:
            async with asyncio.timeout(max(0.0, next_probe - monotonic())):
                message = await websocket.recv()
        except TimeoutError:
            continue
        except ConnectionClosedOK:
            return
        received = monotonic()
        event = _event(message)
        if event is not None and event.get("type") == "player.time_pong":
            response_id = event.get("id")
            if type(response_id) is not int or response_id not in pending:
                continue
            sent = pending[response_id]
            echoed = event.get("client_send")
            if type(echoed) not in (int, float) or echoed != sent:
                continue
            pending.pop(response_id)
            was_ready = clock.ready
            if received - sent <= PROBE_TIMEOUT:
                clock.observe(sent, event.get("server_receive"), event.get("server_send"), received)
            if clock.ready and not was_ready:
                refresh()
            continue
        yield message


async def _receive_changes(websocket, refresh: Callable[[], None], status,
                           on_vote=None, seen_votes=None, clock=None) -> None:
    if seen_votes is None:
        seen_votes = deque(maxlen=512)
    # A successful handshake isn't sufficient: the server must have joined the
    # player's group before we fetch the snapshot, or an update can be missed.
    async with asyncio.timeout(READY_TIMEOUT):
        while True:
            ready = _event(await websocket.recv())
            if ready is not None and ready.get("type") == "player.ready":
                break
    status("Connected")
    refresh()
    clock_enabled = (clock is not None and type(ready.get("sync_version")) is int
                     and ready["sync_version"] == 1)
    messages = _clock_messages(websocket, clock, refresh) if clock_enabled else websocket
    async for message in messages:
        event = _event(message)
        if event is None:
            continue
        if event.get("type") in ("player.changed", "player.ready"):
            refresh()
        elif event.get("type") == "player.vote_received" and on_vote is not None:
            vote_id = event.get("vote_id")
            if type(vote_id) is int and vote_id > 0 and vote_id not in seen_votes:
                seen_votes.append(vote_id)
                pleasant = event.get("pleasant")
                valid_pleasant = type(pleasant) is int and pleasant in (0, 1)
                play_at = event.get("play_at")
                if clock_enabled and finite_number(play_at) and play_at > 0:
                    on_vote(pleasant if valid_pleasant else None, play_at=play_at, vote_id=vote_id)
                elif valid_pleasant:
                    on_vote(pleasant)
                else:
                    on_vote()


async def watch_player_changes(
    api_key: str,
    refresh: Callable[[], None],
    status: Callable[[str], None],
    *,
    url: str | None = None,
    on_vote: Callable[..., None] | None = None,
    clock: ServerClock | None = None,
) -> None:
    """Listen until cancelled, reconnecting with bounded, jittered backoff.

    Callbacks execute on this coroutine's event loop. The refresh callback must
    schedule the existing background HTTP/audio worker, never do I/O itself.
    """
    try:
        socket_url = build_websocket_url(
            API_BASE_URL, url if url is not None else os.environ.get("COSOUND_WS_URL")
        )
    except ValueError:
        status("Check connection URL (polling active)")
        return

    status("Connecting…")
    retry_delay = 1.0
    seen_votes = deque(maxlen=512)
    while True:
        started_at = monotonic()
        denied = False
        try:
            async with _PlayerConnection(
                socket_url,
                additional_headers={"X-API-Key": api_key},
                open_timeout=10,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
                max_size=4096,
                max_queue=16,
            ) as websocket:
                await _receive_changes(websocket, refresh, status, on_vote, seen_votes, clock)
        except asyncio.CancelledError:
            raise
        except InvalidStatus as error:
            denied = error.response.status_code in (401, 403)
        except ConnectionClosed as error:
            denied = error.rcvd is not None and error.rcvd.code in (4401, 4403)
        except (OSError, TimeoutError, WebSocketException):
            pass

        if monotonic() - started_at >= STABLE_CONNECTION_SECONDS:
            retry_delay = 1.0
        if denied:
            status("Authorization failed (polling active)")
            delay = MAX_RETRY_DELAY
        else:
            status("Reconnecting… (polling active)")
            delay = retry_delay
        # Every closure, including a clean one, waits before reconnecting. Do not
        # let an unavailable or rejecting server cause a tight connection loop.
        await asyncio.sleep(random.uniform(delay * 0.75, delay))
        retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
