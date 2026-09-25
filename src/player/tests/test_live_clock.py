import asyncio
import json
import unittest
from time import monotonic
from unittest.mock import Mock, patch

from websockets.asyncio.server import serve

from app import live
from app.sync import ServerClock


def event(kind, **fields):
    return json.dumps({"type": kind, "schema_version": 1, **fields})


class QueueSocket:
    def __init__(self, ready, on_send=None):
        self.incoming = asyncio.Queue()
        self.incoming.put_nowait(ready)
        self.sent = []
        self.on_send = on_send

    async def recv(self):
        return await self.incoming.get()

    async def send(self, message):
        parsed = json.loads(message)
        self.sent.append(parsed)
        if self.on_send:
            self.on_send(parsed)

    async def __aiter__(self):
        while True:
            yield await self.recv()


class LiveClockTests(unittest.IsolatedAsyncioTestCase):
    async def cancel(self, task):
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_capability_is_required_and_old_vote_callback_stays_unchanged(self):
        for capability in (None, 2, True):
            with self.subTest(capability=capability):
                socket = QueueSocket(event("player.ready", sync_version=capability))
                clock, vote, refresh = ServerClock(), Mock(), Mock()
                socket.incoming.put_nowait(event("player.vote_received", vote_id=9, pleasant=1, play_at=1_800_000_000))
                task = asyncio.create_task(live._receive_changes(socket, refresh, Mock(), vote, clock=clock))
                try:
                    async with asyncio.timeout(1):
                        while not vote.called:
                            await asyncio.sleep(0)
                    self.assertEqual(socket.sent, [])
                    self.assertFalse(clock.ready)
                    refresh.assert_called_once_with()
                    vote.assert_called_once_with(1)
                finally:
                    await self.cancel(task)

    async def test_only_matching_probes_lock_clock_while_updates_and_timed_votes_flow(self):
        offset = 1_750_000_000.0
        clock, refresh, vote = ServerClock(), Mock(), Mock()
        socket = QueueSocket(event("player.ready", sync_version=1))

        def on_send(ping):
            now = monotonic() + offset
            valid = {"id": ping["id"], "client_send": ping["client_send"], "server_receive": now, "server_send": now}
            # Unknown IDs and altered echoes must never be used, even if their timing looks plausible.
            socket.incoming.put_nowait(event("player.time_pong", **{**valid, "id": ping["id"] + 500}))
            socket.incoming.put_nowait(event("player.time_pong", **{**valid, "client_send": ping["client_send"] + 1}))
            socket.incoming.put_nowait(event("player.time_pong", **valid))
            socket.incoming.put_nowait(event("player.time_pong", **valid))  # Duplicate.
            socket.incoming.put_nowait(event("player.changed"))
            socket.incoming.put_nowait(event("player.vote_received", vote_id=10, pleasant=0, play_at=offset + 100))

        socket.on_send = on_send
        with patch.object(live, "INITIAL_CLOCK_INTERVAL", 0.005), patch.object(clock, "observe", wraps=clock.observe) as observe:
            task = asyncio.create_task(live._receive_changes(socket, refresh, Mock(), vote, clock=clock))
            try:
                async with asyncio.timeout(2):
                    while not clock.ready or refresh.call_count < 5:
                        await asyncio.sleep(0.001)
                self.assertEqual(observe.call_count, 3)
                self.assertEqual(refresh.call_count, 5)  # Ready, three changes, first clock lock.
                vote.assert_called_once_with(0, play_at=offset + 100, vote_id=10)
                self.assertLess(abs(clock.server_time() - (monotonic() + offset)), 0.010)
            finally:
                await self.cancel(task)

    async def test_malformed_timed_votes_keep_legacy_behavior(self):
        clock, vote = ServerClock(), Mock()
        socket = QueueSocket(event("player.ready", sync_version=1))
        timestamps = (None, True, float("nan"), float("inf"), -1, 10 ** 400)
        for vote_id, timestamp in enumerate(timestamps, start=1):
            socket.incoming.put_nowait(event("player.vote_received", vote_id=vote_id, pleasant=1, play_at=timestamp))
        socket.incoming.put_nowait(event("player.vote_received", vote_id=100, play_at=1_800_000_000))
        task = asyncio.create_task(live._receive_changes(socket, Mock(), Mock(), vote, clock=clock))
        try:
            async with asyncio.timeout(1):
                while vote.call_count < len(timestamps) + 1:
                    await asyncio.sleep(0)
            for call in vote.call_args_list[:-1]:
                self.assertEqual(call.args, (1,))
                self.assertEqual(call.kwargs, {})
            self.assertEqual(vote.call_args.args, (None,))
            self.assertEqual(vote.call_args.kwargs, {"play_at": 1_800_000_000, "vote_id": 100})
        finally:
            await self.cancel(task)

    async def test_real_socket_reconnect_relearns_clock_and_cancel_closes_connection(self):
        clock, refresh = ServerClock(), Mock()
        connected = 0
        second_locked = asyncio.Event()
        closed = asyncio.Event()
        holdover = []
        base_offset = 1_750_000_000.0

        def status(value):
            if value.startswith("Reconnecting"):
                holdover.append(clock.server_time())

        async def handler(websocket):
            nonlocal connected
            connected += 1
            attempt = connected
            probes = 0
            await websocket.send(event("player.ready", sync_version=1))
            async for message in websocket:
                ping = json.loads(message)
                self.assertEqual(ping["type"], "player.time_ping")
                probes += 1
                server_receive = monotonic() + base_offset + (5 if attempt > 1 else 0)
                await websocket.send(event(
                    "player.time_pong", id=ping["id"], client_send=ping["client_send"],
                    server_receive=server_receive, server_send=server_receive,
                ))
                if attempt == 1 and probes == 3:
                    await websocket.close()
                    return
                if attempt == 2 and probes == 4:
                    second_locked.set()
                    await websocket.wait_closed()
                    closed.set()
                    return

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            with patch.object(live, "INITIAL_CLOCK_INTERVAL", 0.005), patch.object(live.random, "uniform", return_value=0):
                task = asyncio.create_task(live.watch_player_changes(
                    "secret", refresh, status, clock=clock,
                    url=f"ws://127.0.0.1:{port}/ws/player/",
                ))
                try:
                    await asyncio.wait_for(second_locked.wait(), 2)
                    self.assertEqual(connected, 2)
                    self.assertTrue(holdover and holdover[0] is not None)
                    self.assertTrue(clock.ready)
                    self.assertLess(abs(clock.server_time() - (monotonic() + base_offset + 5)), 0.010)
                finally:
                    await self.cancel(task)
                await asyncio.wait_for(closed.wait(), 2)


if __name__ == "__main__":
    unittest.main()
