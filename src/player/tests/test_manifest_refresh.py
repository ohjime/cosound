import unittest
from threading import Event, Thread, current_thread
from unittest.mock import Mock, call, patch

import numpy as np

from app import tui


class FakePlayer:
    def __init__(self, fs=48_000):
        self.fs = fs
        self.master_gain = 0.7
        self.queued = []
        self.dequeue_count = 0
        self.queue_threads = []
        self.dequeue_threads = []
        self.vote_chimes = []
        self.vote_chime_volumes = []

    def queue_sound(self, path, gain):
        self.queued.append((path, gain))
        self.queue_threads.append(current_thread().name)

    def dequeue_cosound(self):
        self.dequeue_count += 1
        self.dequeue_threads.append(current_thread().name)

    def set_vote_chime(self, samples=None):
        self.vote_chimes.append(samples)

    def set_vote_chime_volume(self, volume):
        self.vote_chime_volumes.append(volume)


class ManifestRefreshTests(unittest.TestCase):
    def test_program_switch_is_a_new_playback_state_even_with_same_layers(self):
        first = {"program_id": 1, "layers": [{"sound_id": 7, "gain": 1.0}]}
        second = {"program_id": 2, "layers": [{"sound_id": 7, "gain": 1.0}]}
        self.assertNotEqual(
            tui.CosoundPlayerApp._signature_of(first),
            tui.CosoundPlayerApp._signature_of(second),
        )

    def test_known_layers_keep_existing_manifest_and_skip_network_work(self):
        manifest = {"1": "/conditioned/1.wav"}
        layers = [{"sound_id": 1, "gain": 0.75}]
        player = FakePlayer()

        with (
            patch.object(tui, "get_latest_manifest") as get_manifest,
            patch.object(tui, "get_sound") as get_sound,
            patch.object(tui, "condition_manifest") as condition_manifest,
        ):
            tui._refresh_missing_manifest_entries(
                "player-key", manifest, layers, player.fs
            )

        get_manifest.assert_not_called()
        get_sound.assert_not_called()
        condition_manifest.assert_not_called()

        tui._queue_manifest_layers(manifest, layers, player)
        self.assertEqual(player.queued, [("/conditioned/1.wav", 0.75)])
        self.assertEqual(player.dequeue_count, 1)

    def test_missing_layers_are_downloaded_conditioned_merged_then_queued(self):
        manifest = {"1": "/conditioned/1.wav"}
        layers = [
            {"sound_id": 1, "gain": 0.25},
            {"sound_id": 2, "gain": 0.5},
            {"sound_id": 2, "gain": 0.5},
            {"sound_id": 3, "gain": 0.75},
        ]
        player = FakePlayer()
        remote_manifest = {
            "1": "https://sounds.example/1",
            "2": "https://sounds.example/2",
            "3": "https://sounds.example/3",
            "4": "https://sounds.example/4",
        }

        with (
            patch.object(
                tui, "get_latest_manifest", return_value=remote_manifest
            ) as get_manifest,
            patch.object(
                tui,
                "get_sound",
                side_effect=lambda sound_id, _url: f"/downloaded/{sound_id}",
            ) as get_sound,
            patch.object(
                tui,
                "condition_manifest",
                return_value={
                    "2": "/conditioned/2.wav",
                    "3": "/conditioned/3.wav",
                },
            ) as condition_manifest,
        ):
            tui._refresh_missing_manifest_entries(
                "player-key", manifest, layers, player.fs
            )

        get_manifest.assert_called_once_with("player-key")
        self.assertEqual(
            get_sound.call_args_list,
            [
                call("2", "https://sounds.example/2"),
                call("3", "https://sounds.example/3"),
            ],
        )
        condition_manifest.assert_called_once_with(
            {"2": "/downloaded/2", "3": "/downloaded/3"},
            tui.CONDITIONED_DIR,
            48_000,
        )
        self.assertEqual(
            manifest,
            {
                "1": "/conditioned/1.wav",
                "2": "/conditioned/2.wav",
                "3": "/conditioned/3.wav",
            },
        )

        tui._queue_manifest_layers(manifest, layers, player)
        self.assertEqual(
            player.queued,
            [
                ("/conditioned/1.wav", 0.25),
                ("/conditioned/2.wav", 0.5),
                ("/conditioned/2.wav", 0.5),
                ("/conditioned/3.wav", 0.75),
            ],
        )
        self.assertEqual(player.dequeue_count, 1)

    def test_manifest_refresh_errors_propagate_without_partial_update(self):
        manifest = {"1": "/conditioned/1.wav"}
        layers = [{"sound_id": 2, "gain": 1.0}]

        with (
            patch.object(
                tui, "get_latest_manifest", side_effect=OSError("offline")
            ),
            patch.object(tui, "get_sound") as get_sound,
            patch.object(tui, "condition_manifest") as condition_manifest,
        ):
            with self.assertRaisesRegex(OSError, "offline"):
                tui._refresh_missing_manifest_entries(
                    "player-key", manifest, layers, 48_000
                )

        get_sound.assert_not_called()
        condition_manifest.assert_not_called()
        self.assertEqual(manifest, {"1": "/conditioned/1.wav"})

    def test_unresolved_layer_does_not_trigger_playback_transition(self):
        manifest = {"1": "/conditioned/1.wav"}
        layers = [{"sound_id": 2, "gain": 1.0}]
        player = FakePlayer()

        with (
            patch.object(tui, "get_latest_manifest", return_value={"1": "known"}),
            patch.object(tui, "get_sound") as get_sound,
            patch.object(tui, "condition_manifest") as condition_manifest,
        ):
            with self.assertRaisesRegex(RuntimeError, r"sound ID\(s\): 2"):
                tui._refresh_missing_manifest_entries(
                    "player-key", manifest, layers, player.fs
                )
                tui._queue_manifest_layers(manifest, layers, player)

        get_sound.assert_not_called()
        condition_manifest.assert_not_called()
        self.assertEqual(manifest, {"1": "/conditioned/1.wav"})
        self.assertEqual(player.queued, [])
        self.assertEqual(player.dequeue_count, 0)

    def test_refresh_requests_are_coalesced_while_worker_is_running(self):
        app = tui.CosoundPlayerApp("player-key", {}, FakePlayer())

        with (
            patch.object(app, "_show_refreshing"),
            patch.object(app, "_refresh_cosound_worker") as start_worker,
        ):
            app.refresh_cosound()
            app.refresh_cosound()
            app.refresh_cosound()

        start_worker.assert_called_once_with()
        self.assertEqual(app._refresh_generation, 3)
        self.assertTrue(app._refresh_worker_running)

    def test_state_refresh_interval_defaults_to_thirty_seconds(self):
        app = tui.CosoundPlayerApp("player-key", {}, FakePlayer())
        meter_timer = Mock()
        state_refresh_timer = Mock()

        self.assertEqual(app._state_refresh_interval_seconds, 30)
        self.assertIsNone(app._state_refresh_timer)

        with (
            patch.object(app, "_show_volume"),
            patch.object(
                app,
                "set_interval",
                side_effect=[meter_timer, state_refresh_timer],
            ) as set_interval,
            patch.object(app, "refresh_cosound") as refresh,
            patch.object(app, "_watch_live_updates"),
        ):
            app.on_mount()

        self.assertEqual(set_interval.call_args_list[0].args[0], tui.METER_INTERVAL)
        self.assertEqual(
            set_interval.call_args_list[1],
            call(tui.REFRESH_INTERVAL, refresh),
        )
        self.assertIs(app._state_refresh_timer, state_refresh_timer)

    def test_missing_or_malformed_state_refresh_interval_preserves_current_timer(self):
        app = tui.CosoundPlayerApp("player-key", {}, FakePlayer())
        current_timer = Mock()
        app._state_refresh_interval_seconds = 45
        app._state_refresh_timer = current_timer
        malformed_snapshots = (
            {},
            {"runtime": None},
            {"runtime": []},
            {"runtime": {}},
            {"runtime": {"state_refresh_interval_seconds": True}},
            {"runtime": {"state_refresh_interval_seconds": 4}},
            {"runtime": {"state_refresh_interval_seconds": 30.0}},
            {"runtime": {"state_refresh_interval_seconds": "30"}},
        )

        with patch.object(app, "set_interval") as set_interval:
            for info in malformed_snapshots:
                with self.subTest(info=info):
                    app._sync_state_refresh_interval(info)

        self.assertEqual(app._state_refresh_interval_seconds, 45)
        self.assertIs(app._state_refresh_timer, current_timer)
        current_timer.stop.assert_not_called()
        set_interval.assert_not_called()

    def test_unchanged_state_refresh_interval_keeps_existing_timer(self):
        app = tui.CosoundPlayerApp("player-key", {}, FakePlayer())
        current_timer = Mock()
        app._state_refresh_timer = current_timer

        with patch.object(app, "set_interval") as set_interval:
            app._sync_state_refresh_interval(
                {"runtime": {"state_refresh_interval_seconds": 30}}
            )

        self.assertIs(app._state_refresh_timer, current_timer)
        current_timer.stop.assert_not_called()
        set_interval.assert_not_called()

    def test_valid_runtime_interval_replaces_the_existing_timer(self):
        app = tui.CosoundPlayerApp("player-key", {}, FakePlayer())
        old_timer = Mock()
        new_timer = Mock()
        app._state_refresh_timer = old_timer
        info = {
            "name": "Hall",
            "manager": "Manager",
            "layers": [],
            "runtime": {"state_refresh_interval_seconds": 15},
        }

        with patch.object(
            app, "set_interval", return_value=new_timer
        ) as set_interval:
            app._sync_state_refresh_interval(info)

        self.assertEqual(app._state_refresh_interval_seconds, 15)
        old_timer.stop.assert_called_once_with()
        set_interval.assert_called_once_with(15, app.refresh_cosound)
        self.assertIs(app._state_refresh_timer, new_timer)

    def test_runtime_interval_updates_even_when_layer_preparation_fails(self):
        app = tui.CosoundPlayerApp("player-key", {}, FakePlayer())
        old_timer = Mock()
        new_timer = Mock()
        app._state_refresh_timer = old_timer
        info = {
            "layers": [{"sound_id": 2, "gain": 1.0}],
            "runtime": {"state_refresh_interval_seconds": 15},
        }

        with (
            patch.object(tui, "get_player_info", return_value=info),
            patch.object(
                tui, "get_latest_manifest", side_effect=OSError("offline")
            ),
            patch.object(app, "set_interval", return_value=new_timer),
            patch.object(
                app,
                "call_from_thread",
                side_effect=lambda callback, *args: callback(*args),
            ),
        ):
            with self.assertRaisesRegex(OSError, "offline"):
                app._run_refresh()

        self.assertEqual(app._state_refresh_interval_seconds, 15)
        old_timer.stop.assert_called_once_with()
        self.assertIs(app._state_refresh_timer, new_timer)

    def test_new_program_chime_updates_even_when_its_sound_is_unavailable(self):
        player = FakePlayer()
        app = tui.CosoundPlayerApp("player-key", {}, player)
        app._vote_chime_version = "old-version"
        info = {
            "program_id": 2,
            "layers": [{"sound_id": 2, "gain": 1.0}],
            "chime": {"url": "", "version": "", "volume": 0.4},
        }
        with (
            patch.object(tui, "get_player_info", return_value=info),
            patch.object(tui, "get_latest_manifest", side_effect=OSError("offline")),
            patch.object(tui, "prune_vote_chimes"),
            patch.object(app, "call_from_thread"),
        ):
            with self.assertRaisesRegex(OSError, "offline"):
                app._run_refresh()

        self.assertEqual(player.vote_chimes, [None])
        self.assertEqual(player.vote_chime_volumes, [0.4])
        self.assertIsNone(app._vote_chime_version)

    def test_slow_refresh_finishes_before_latest_coalesced_state(self):
        manifest = {"1": "/conditioned/1.wav"}
        player = FakePlayer()
        app = tui.CosoundPlayerApp("player-key", manifest, player)
        old_info = {
            "name": "Old response",
            "layers": [{"sound_id": 2, "gain": 0.25}],
        }
        new_info = {
            "name": "New response",
            "layers": [{"sound_id": 3, "gain": 0.75}],
        }
        old_conditioning_started = Event()
        release_old_conditioning = Event()
        conditioning_order = []
        conditioning_threads = []
        thread_errors = []

        def condition(downloaded, _out_dir, _target_fs):
            sound_id = next(iter(downloaded))
            conditioning_order.append(sound_id)
            conditioning_threads.append(current_thread().name)
            if sound_id == "2":
                old_conditioning_started.set()
                if not release_old_conditioning.wait(timeout=2):
                    raise TimeoutError("old conditioning was not released")
            return {sound_id: f"/conditioned/{sound_id}.wav"}

        def run_refresh_loop():
            try:
                app._run_refresh_loop()
            except Exception as error:  # pragma: no cover - asserted below
                thread_errors.append(error)

        def apply_immediately(callback, *args):
            callback(*args)

        def track_applied_state(info, changed):
            if changed:
                app._cosound_signature = app._signature_of(info)

        with (
            patch.object(
                tui,
                "get_player_info",
                side_effect=[old_info, new_info],
            ),
            patch.object(
                tui,
                "get_latest_manifest",
                return_value={"2": "remote-2", "3": "remote-3"},
            ),
            patch.object(
                tui,
                "get_sound",
                side_effect=lambda sound_id, _path: f"/downloaded/{sound_id}",
            ),
            patch.object(tui, "condition_manifest", side_effect=condition),
            patch.object(app, "call_from_thread", side_effect=apply_immediately),
            patch.object(
                app, "_apply_state", side_effect=track_applied_state
            ) as apply_state,
            patch.object(app, "_show_refreshing") as show_refreshing,
        ):
            with app._refresh_lock:
                app._refresh_generation = 1
                app._refresh_worker_running = True
            worker_thread = Thread(
                target=run_refresh_loop, name="serial-refresh"
            )
            worker_thread.start()
            self.assertTrue(old_conditioning_started.wait(timeout=2))

            with app._refresh_lock:
                # Two requests arrive while generation 1 is still conditioning.
                app._refresh_generation = 2
                app._refresh_generation = 3

            self.assertEqual(conditioning_order, ["2"])
            self.assertEqual(player.queued, [])

            release_old_conditioning.set()
            worker_thread.join(timeout=2)
            self.assertFalse(worker_thread.is_alive())

        self.assertEqual(thread_errors, [])
        self.assertEqual(conditioning_order, ["2", "3"])
        self.assertEqual(conditioning_threads, ["serial-refresh", "serial-refresh"])
        self.assertEqual(
            manifest,
            {
                "1": "/conditioned/1.wav",
                "2": "/conditioned/2.wav",
                "3": "/conditioned/3.wav",
            },
        )
        self.assertEqual(
            player.queued,
            [
                ("/conditioned/2.wav", 0.25),
                ("/conditioned/3.wav", 0.75),
            ],
        )
        self.assertEqual(player.dequeue_count, 2)
        self.assertEqual(
            player.queue_threads, ["serial-refresh", "serial-refresh"]
        )
        self.assertEqual(
            player.dequeue_threads, ["serial-refresh", "serial-refresh"]
        )
        self.assertEqual(
            apply_state.call_args_list,
            [call(old_info, True), call(new_info, True)],
        )
        show_refreshing.assert_called_once_with()
        self.assertEqual(app._refresh_generation, 3)
        self.assertFalse(app._refresh_worker_running)

    def test_chime_updates_when_layers_do_not_and_unchanged_version_is_cached(self):
        player = FakePlayer()
        info = {
            "layers": [{"sound_id": 1, "gain": 0.5}],
            "chime": {
                "url": "https://media.example/chime?signature=one",
                "version": "chimes/player-1/upload.wav",
            },
        }
        app = tui.CosoundPlayerApp("key", {"1": "/conditioned/1.wav"}, player)
        app._cosound_signature = app._signature_of(info)
        prepared = np.full(20, 0.05, dtype=np.float32)

        with (
            patch.object(tui, "get_player_info", return_value=info),
            patch.object(
                tui, "get_vote_chime", return_value="/vote-chimes/version"
            ) as download,
            patch.object(tui, "load_vote_chime", return_value=prepared) as decode,
            patch.object(tui, "prune_vote_chimes") as prune,
            patch.object(app, "call_from_thread") as call_from_thread,
        ):
            app._run_refresh()
            # A refreshed signed URL with the same stable version is not fetched.
            info["chime"]["url"] = "https://media.example/chime?signature=two"
            app._run_refresh()

        download.assert_called_once_with(
            "chimes/player-1/upload.wav",
            "https://media.example/chime?signature=one",
        )
        decode.assert_called_once_with("/vote-chimes/version", player.fs)
        self.assertEqual(len(player.vote_chimes), 1)
        np.testing.assert_array_equal(player.vote_chimes[0], prepared)
        self.assertEqual(player.queued, [])
        self.assertEqual(player.dequeue_count, 0)
        self.assertEqual(call_from_thread.call_count, 4)
        prune.assert_called_once_with("chimes/player-1/upload.wav")

    def test_empty_descriptor_resets_custom_chime_to_generated_fallback(self):
        player = FakePlayer()
        app = tui.CosoundPlayerApp("key", {}, player)
        app._vote_chime_version = "old-version"

        with (
            patch.object(tui, "get_vote_chime") as download,
            patch.object(tui, "load_vote_chime") as decode,
            patch.object(tui, "prune_vote_chimes") as prune,
        ):
            app._sync_vote_chime({"chime": {"url": "", "version": ""}})

        self.assertEqual(player.vote_chimes, [None])
        self.assertIsNone(app._vote_chime_version)
        download.assert_not_called()
        decode.assert_not_called()
        prune.assert_called_once_with()

    def test_volume_applies_without_refetching_an_unchanged_chime(self):
        player = FakePlayer()
        app = tui.CosoundPlayerApp("key", {}, player)
        app._vote_chime_version = "same-version"
        descriptor = {
            "url": "https://media.example/chime",
            "version": "same-version",
            "volume": 0.25,
        }

        with (
            patch.object(tui, "get_vote_chime") as download,
            patch.object(tui, "load_vote_chime") as decode,
        ):
            app._sync_vote_chime({"chime": descriptor})
            # The built-in tone takes the same setting, with no file involved.
            app._vote_chime_version = None
            app._sync_vote_chime({"chime": {"url": "", "version": "", "volume": 1.0}})

        self.assertEqual(player.vote_chime_volumes, [0.25, 1.0])
        download.assert_not_called()
        decode.assert_not_called()

    def test_omitted_volume_leaves_the_current_level_alone(self):
        # An older server, and the /cosound fallback, say nothing about volume.
        player = FakePlayer()
        app = tui.CosoundPlayerApp("key", {}, player)
        app._vote_chime_version = "same-version"

        app._sync_vote_chime({"layers": []})
        app._sync_vote_chime(
            {"chime": {"url": "https://media/x", "version": "same-version"}}
        )
        self.assertEqual(player.vote_chime_volumes, [])

        for volume in ("loud", None, True):
            with self.subTest(volume=volume), self.assertRaises(ValueError):
                app._sync_vote_chime({"chime": {"volume": volume}})
        self.assertEqual(player.vote_chime_volumes, [])

    def test_legacy_or_mismatched_descriptor_preserves_last_good_chime(self):
        player = FakePlayer()
        app = tui.CosoundPlayerApp("key", {}, player)
        app._vote_chime_version = "last-good-version"

        # An old server omits the field entirely; that is a compatibility no-op.
        app._sync_vote_chime({"layers": []})
        for descriptor in (
            {"url": "", "version": "unexpected"},
            {"url": "https://media/new", "version": ""},
            {"url": None, "version": None},
            [],
        ):
            with self.subTest(descriptor=descriptor), self.assertRaises(ValueError):
                app._sync_vote_chime({"chime": descriptor})

        self.assertEqual(player.vote_chimes, [])
        self.assertEqual(app._vote_chime_version, "last-good-version")

    def test_decode_failure_discards_cache_and_retries_without_losing_last_good(self):
        player = FakePlayer()
        app = tui.CosoundPlayerApp("key", {}, player)
        app._vote_chime_version = "last-good-version"
        info = {
            "chime": {
                "url": "https://media/new",
                "version": "new-version",
            }
        }

        with (
            patch.object(
                tui, "get_vote_chime", return_value="/vote-chimes/new-version"
            ) as download,
            patch.object(
                tui, "load_vote_chime", side_effect=ValueError("corrupt audio")
            ) as decode,
            patch.object(tui, "discard_vote_chime") as discard,
        ):
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, "corrupt audio"):
                    app._sync_vote_chime(info)

        self.assertEqual(download.call_count, 2)
        self.assertEqual(decode.call_count, 2)
        self.assertEqual(
            discard.call_args_list,
            [call("new-version"), call("new-version")],
        )
        self.assertEqual(player.vote_chimes, [])
        self.assertEqual(app._vote_chime_version, "last-good-version")

    def test_bad_custom_chime_preserves_last_good_and_does_not_block_state(self):
        player = FakePlayer()
        info = {
            "name": "Hall",
            "layers": [],
            "chime": {"url": "https://media/new", "version": "new-version"},
        }
        app = tui.CosoundPlayerApp("key", {}, player)
        app._vote_chime_version = "last-good-version"

        with (
            patch.object(tui, "get_player_info", return_value=info),
            patch.object(tui, "get_vote_chime", side_effect=OSError("offline")),
            patch.object(app, "call_from_thread") as call_from_thread,
        ):
            app._run_refresh()

        self.assertEqual(player.vote_chimes, [])
        self.assertEqual(app._vote_chime_version, "last-good-version")
        self.assertEqual(
            call_from_thread.call_args_list,
            [
                call(app._sync_state_refresh_interval, info),
                call(app._apply_state, info, True),
            ],
        )


if __name__ == "__main__":
    unittest.main()
