"""Exercise state refresh through preparation and playback dispatch, without a DAC."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from app import tui
from app.playback import PlaybackPlan
from app.sync import ServerClock


def snapshot(revision="first", *, sound_id=1, gain=0.5, previous=None):
    return {
        "name": "Shared room",
        "program_id": 7,
        "layers": [{"sound_id": sound_id, "gain": gain}],
        "playback_sync": {
            "version": 1,
            "revision": revision,
            "epoch": 1_000.0,
            "effective_at": 1_010.0 if revision == "first" else 1_020.0,
            "fade_seconds": 8.0,
            "previous_layers": previous or [],
        },
    }


class RecordingPlayer:
    """Record installed plans while using the real descriptor and clock types."""

    def __init__(self):
        self.fs = 44_100
        self.master_gain = 0.7
        self.clock = ServerClock()
        for sent in (1.0, 2.0, 3.0):
            self.clock.observe(sent, 1_000.0 + sent + 0.005,
                               1_000.0 + sent + 0.005, sent + 0.010)
        self.current_plan = None
        self.scheduled = []
        self.queued = []
        self.dequeue_count = 0

    def schedule_cosound(self, manifest, layers, descriptor):
        plan = PlaybackPlan.parse(descriptor, layers)
        self.scheduled.append((dict(manifest), plan))
        self.current_plan = plan

    def queue_sound(self, path, gain):
        self.queued.append((path, gain))

    def dequeue_cosound(self):
        self.dequeue_count += 1


class SyncRefreshTests(unittest.TestCase):
    def setUp(self):
        self.player = RecordingPlayer()
        self.app = tui.CosoundPlayerApp(
            "player-token", {"1": "/conditioned/1.wav"}, self.player
        )
        self.initial = snapshot()
        self.player.current_plan = PlaybackPlan.parse(
            self.initial["playback_sync"], self.initial["layers"]
        )
        self.app._cosound_signature = self.app._signature_of(self.initial)
        self.get_info = self.patch(tui, "get_player_info")
        self.get_manifest = self.patch(tui, "get_latest_manifest", return_value={})
        self.get_sound = self.patch(
            tui, "get_sound",
            side_effect=lambda sound_id, _url: f"/downloaded/{sound_id}",
        )
        self.condition = self.patch(
            tui, "condition_manifest",
            side_effect=lambda files, _directory, _rate, **_options: {
                sound_id: f"/conditioned/{sound_id}.wav" for sound_id in files
            },
        )
        self.patch(
            self.app, "call_from_thread",
            side_effect=lambda callback, *args: callback(*args),
        )
        self.apply_state = self.patch(
            self.app, "_apply_state", side_effect=self.remember_applied_state
        )

    def patch(self, target, attribute, **kwargs):
        replacement = patch.object(target, attribute, **kwargs)
        self.addCleanup(replacement.stop)
        return replacement.start()

    def remember_applied_state(self, info, changed):
        # Only the terminal rendering is replaced; the real refresh worker,
        # preparation, signature comparison, and playback dispatch all run.
        if changed:
            self.app._cosound_signature = self.app._signature_of(info)

    def refresh(self, info):
        self.get_info.return_value = info
        self.app._run_refresh()

    def test_unchanged_revision_refreshes_metadata_without_reloading_audio(self):
        info = deepcopy(self.initial)
        info["name"] = "Renamed room"
        original_plan = self.player.current_plan

        self.refresh(info)
        self.refresh(info)

        self.assertTrue(self.player.clock.ready)
        self.assertIs(self.player.current_plan, original_plan)
        self.assertEqual(self.player.scheduled, [])
        self.assertEqual(self.player.queued, [])
        self.assertEqual(self.player.dequeue_count, 0)
        self.get_manifest.assert_not_called()
        self.get_sound.assert_not_called()
        self.condition.assert_not_called()
        self.apply_state.assert_called_with(info, False)

    def test_new_revision_reschedules_even_when_layers_are_identical(self):
        info = snapshot("second")

        self.refresh(info)
        self.refresh(info)

        self.assertEqual(len(self.player.scheduled), 1)
        self.assertEqual(self.player.current_plan.revision, "second")
        self.assertEqual(self.player.current_plan.target, {"1": 0.5})
        self.assertEqual(self.player.scheduled[0][0], {"1": "/conditioned/1.wav"})
        self.assertEqual(self.player.dequeue_count, 0)
        self.get_manifest.assert_not_called()
        self.condition.assert_not_called()

    def test_new_target_is_conditioned_strictly_at_48k_for_a_44k_device(self):
        info = snapshot("second", sound_id=2)
        self.get_manifest.return_value = {"2": "https://sounds.example/2"}

        self.refresh(info)

        self.get_sound.assert_called_once_with("2", "https://sounds.example/2")
        self.condition.assert_called_once_with(
            {"2": "/downloaded/2"}, tui.CONDITIONED_DIR, 48_000, strict=True
        )
        manifest, plan = self.player.scheduled[0]
        self.assertEqual(manifest["2"], "/conditioned/2.wav")
        self.assertEqual(plan.target, {"2": 0.5})
        self.assertEqual(self.player.fs, 44_100)
        self.assertEqual(self.player.queued, [])

    def test_failed_target_conditioning_preserves_mix_and_allows_retry(self):
        info = snapshot("second", sound_id=2)
        self.get_manifest.return_value = {"2": "remote-2"}
        self.condition.side_effect = OSError("decoder unavailable")
        original_plan = self.player.current_plan
        original_signature = self.app._cosound_signature

        with self.assertRaisesRegex(RuntimeError, "decoder unavailable"):
            self.refresh(info)

        self.assertIs(self.player.current_plan, original_plan)
        self.assertEqual(self.app._cosound_signature, original_signature)
        self.assertEqual(self.app.manifest, {"1": "/conditioned/1.wav"})
        self.assertEqual(self.player.scheduled, [])
        self.apply_state.assert_not_called()

        self.condition.side_effect = None
        self.condition.return_value = {"2": "/conditioned/2.wav"}
        self.refresh(info)

        self.assertEqual(self.player.current_plan.revision, "second")
        self.assertEqual(self.app.manifest["2"], "/conditioned/2.wav")
        self.assertEqual(len(self.player.scheduled), 1)

    def test_unavailable_previous_asset_does_not_block_current_mix(self):
        info = snapshot("second", previous=[{"sound_id": 99, "gain": 0.75}])
        # The server no longer exposes this previous-only sound in its manifest.
        self.get_manifest.return_value = {"1": "remote-1"}

        self.refresh(info)

        self.assertEqual(self.player.current_plan.revision, "second")
        self.assertEqual(self.player.current_plan.target, {"1": 0.5})
        self.assertEqual(self.player.scheduled[0][0], {"1": "/conditioned/1.wav"})
        self.get_sound.assert_not_called()
        self.condition.assert_not_called()
        self.apply_state.assert_called_once_with(info, True)

    def test_previous_asset_conditioning_failure_does_not_block_current_mix(self):
        info = snapshot("second", previous=[{"sound_id": 99, "gain": 0.75}])
        self.get_manifest.return_value = {"99": "remote-99"}
        self.condition.side_effect = OSError("old asset is corrupt")

        self.refresh(info)

        self.condition.assert_called_once_with(
            {"99": "/downloaded/99"}, tui.CONDITIONED_DIR, 48_000, strict=True
        )
        self.assertEqual(self.player.current_plan.revision, "second")
        self.assertEqual(self.player.current_plan.target, {"1": 0.5})
        self.assertNotIn("99", self.app.manifest)
        self.apply_state.assert_called_once_with(info, True)

    def test_malformed_timeline_preserves_the_installed_mix_and_signature(self):
        original_plan = self.player.current_plan
        original_signature = self.app._cosound_signature
        descriptor = snapshot("second")["playback_sync"]
        malformed = (
            {}, [], "unexpected",
            {**descriptor, "version": 2},
            {**descriptor, "epoch": "bad"},
            {**descriptor, "fade_seconds": float("nan")},
            {**descriptor, "effective_at": 900.0},
            {**descriptor, "previous_layers": "bad"},
        )
        for value in malformed:
            with self.subTest(descriptor=value):
                info = snapshot("second")
                info["playback_sync"] = value
                with self.assertRaises(ValueError):
                    self.refresh(info)
                self.assertIs(self.player.current_plan, original_plan)
                self.assertEqual(self.app._cosound_signature, original_signature)
                self.assertEqual(self.app.manifest, {"1": "/conditioned/1.wav"})

        self.assertEqual(self.player.scheduled, [])
        self.assertEqual(self.player.queued, [])
        self.get_manifest.assert_not_called()
        self.condition.assert_not_called()
        self.apply_state.assert_not_called()

    def test_legacy_snapshot_uses_existing_queue_path_and_skips_unchanged_mix(self):
        self.app._cosound_signature = None
        self.player.current_plan = None
        info = {"program_id": 7, "layers": [{"sound_id": 1, "gain": 0.25}]}

        self.refresh(info)
        self.refresh(info)

        self.assertEqual(self.player.queued, [("/conditioned/1.wav", 0.25)])
        self.assertEqual(self.player.dequeue_count, 1)
        self.assertEqual(self.player.scheduled, [])
        self.get_manifest.assert_not_called()
        self.condition.assert_not_called()
        self.apply_state.assert_called_with(info, False)


if __name__ == "__main__":
    unittest.main()
