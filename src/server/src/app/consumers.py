"""Authenticated player notifications and clock synchronization probes."""

import asyncio
import json
import logging
import math
import time
from collections import deque
from contextlib import suppress

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.http.request import split_domain_port, validate_host
from redis.exceptions import RedisError

from core.models import Player
from core.player_events import player_group_name

logger = logging.getLogger(__name__)
SUBSCRIPTION_REFRESH_SECONDS = 60
CHANNEL_TIMEOUT_SECONDS = 3
MAX_CLOCK_PROBES_PER_SECOND = 16


@database_sync_to_async
def authenticated_player_id(token):
    return Player.objects.filter(token=token).values_list("pk", flat=True).first()


class PlayerConsumer(AsyncJsonWebsocketConsumer):
    """Each credential can subscribe only to the player it belongs to."""

    async def __call__(self, scope, receive, send):
        self.group_name = None
        self.maintenance = None
        self.close_sent = False
        self.disconnected = False
        self.clock_probes = deque()
        try:
            return await super().__call__(scope, receive, send)
        except RedisError:
            logger.warning("Player notification transport unavailable", exc_info=True)
            if not self.close_sent and not self.disconnected:
                await send({"type": "websocket.close", "code": 1013})
        finally:
            # Also runs if the Redis receive loop fails without a disconnect.
            if self.maintenance is not None:
                self.maintenance.cancel()
                try:
                    with suppress(asyncio.CancelledError):
                        await self.maintenance
                except Exception:
                    logger.warning("Player subscription cleanup failed", exc_info=True)
            if self.group_name is not None:
                try:
                    async with asyncio.timeout(CHANNEL_TIMEOUT_SECONDS):
                        await self.channel_layer.group_discard(
                            self.group_name, self.channel_name
                        )
                except Exception:
                    logger.warning("Could not remove player subscription", exc_info=True)

    async def connect(self):
        headers = self.scope.get("headers", [])
        hosts = [value for name, value in headers if name.lower() == b"host"]
        tokens = [value for name, value in headers if name.lower() == b"x-api-key"]
        if (
            len(hosts) != 1 or len(tokens) != 1
            or not 1 <= len(tokens[0]) <= 64
            or any(value < 33 or value > 126 for value in tokens[0])
        ):
            await self.close(code=4401)
            return
        domain, _ = split_domain_port(hosts[0].decode("latin1"))
        allowed_hosts = settings.ALLOWED_HOSTS
        if not allowed_hosts and settings.DEBUG:
            allowed_hosts = [".localhost", "127.0.0.1", "[::1]"]
        if not domain or not validate_host(domain, allowed_hosts):
            await self.close(code=4403)
            return
        # No cookie or query-string authentication: the Python player supplies
        # its existing API key in the upgrade request's header.
        self.token = tokens[0].decode("latin1")
        self.player_id = await authenticated_player_id(self.token)
        if self.player_id is None:
            await self.close(code=4401)
            return
        self.group_name = player_group_name(self.player_id)
        try:
            await self._subscribe()
        except Exception:
            logger.warning("Player subscription unavailable", exc_info=True)
            await self.close(code=1013)
            return
        await self.accept()
        # The client refreshes only after this acknowledgement, closing the gap
        # between its initial HTTP snapshot and the subscription becoming live.
        await self.send_json({
            "type": "player.ready", "schema_version": 1, "sync_version": 1,
        })
        self.maintenance = asyncio.create_task(self._maintain_subscription())

    async def _subscribe(self):
        async with asyncio.timeout(CHANNEL_TIMEOUT_SECONDS):
            await self.channel_layer.group_add(self.group_name, self.channel_name)

    async def _authorized(self):
        if await authenticated_player_id(self.token) != self.player_id:
            await self.close(code=4401)
            return False
        return True

    async def _maintain_subscription(self):
        try:
            while True:
                await asyncio.sleep(SUBSCRIPTION_REFRESH_SECONDS)
                if not await self._authorized():
                    return
                # Renew expiry for installations that remain connected for days.
                await self._subscribe()
        except Exception:
            logger.warning("Player subscription interrupted", exc_info=True)
            await self.close(code=1013)

    async def player_changed(self, event):
        if await self._authorized():
            # Never forward arbitrary event fields or a model/credential dump.
            await self.send_json({"type": "player.changed", "schema_version": 1})

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        # Capture receipt before parsing/authentication. The client subtracts
        # this processing interval from its round trip, including any DB wait.
        received_at = time.time()
        if bytes_data is not None or not text_data or len(text_data) > 512:
            await self.close(code=1008)
            return
        try:
            probe = json.loads(text_data)
        except (ValueError, TypeError):
            await self.close(code=1008)
            return
        if not (
            isinstance(probe, dict)
            and probe.get("type") == "player.time_ping"
            and type(probe.get("schema_version")) is int
            and probe["schema_version"] == 1
            and type(probe.get("id")) is int
            and 0 <= probe["id"] <= 2**53 - 1
            and type(probe.get("client_send")) in (int, float)
            and abs(probe["client_send"]) <= 1e15
            and math.isfinite(probe["client_send"])
        ):
            await self.close(code=1008)
            return
        now = time.monotonic()
        while self.clock_probes and self.clock_probes[0] <= now - 1.0:
            self.clock_probes.popleft()
        if len(self.clock_probes) >= MAX_CLOCK_PROBES_PER_SECOND:
            await self.close(code=1008)
            return
        self.clock_probes.append(now)
        if await self._authorized():
            await self.send_json({
                "type": "player.time_pong", "schema_version": 1,
                "id": probe["id"], "client_send": probe["client_send"],
                "server_receive": received_at, "server_send": time.time(),
            })

    async def player_vote_received(self, event):
        vote_id = event.get("vote_id")
        pleasant = event.get("pleasant")
        if (
            type(vote_id) is int and vote_id > 0
            and type(pleasant) is int and pleasant in (0, 1)
            and await self._authorized()
        ):
            message = {
                "type": "player.vote_received", "schema_version": 1,
                "vote_id": vote_id, "pleasant": pleasant,
            }
            play_at = event.get("play_at")
            if type(play_at) in (int, float) and abs(play_at) <= 1e15 and math.isfinite(play_at):
                message["play_at"] = play_at
            await self.send_json(message)

    async def close(self, code=None, reason=None):
        if not self.close_sent and not self.disconnected:
            self.close_sent = True
            await super().close(code=code, reason=reason)

    async def disconnect(self, close_code):
        self.disconnected = True
