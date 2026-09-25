"""Exercise independent audio devices without opening physical speakers."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from app.devices import OutputDevice
from app.player import SoundDevicePlayer
from app.playback import CORRECTION_SLEW_SECONDS, MAX_CORRECTION, PlaybackPlan, loop_chunk


def timeline(revision="one", at=1010.0, previous=None, fade=8.0):
    return {"version": 1, "revision": revision, "epoch": 1010.0,
            "effective_at": at, "fade_seconds": fade,
            "previous_layers": previous or []}


class SynchronizedPlaybackTests(unittest.TestCase):
    def player(self, fs=48000, anchor=(0.0, 0.0)):
        device = OutputDevice(None, "Test", 1, fs, "Test")
        with patch("app.player.detect_output", return_value=device), patch("app.player.sd.OutputStream") as stream:
            stream.return_value.time = 100.0
            player = SoundDevicePlayer(reverb_amount=0, master_gain=1)
        player.clock = SimpleNamespace(ready=True, server_time=lambda value=None: 1000 + (value or 0))
        player._audio_clock_anchor = anchor
        player._dac_timing_available = True
        # Observe the actual mixed source without a room's reverb or filtering.
        player.renderer = Mock(rotation_deg_per_s=0)
        player.renderer.render.side_effect = lambda sources, frames: (
            sum((src["signal"] for src in sources), np.zeros((frames, 1), np.float32)),
            np.zeros(frames, np.float32),
        )
        player.reverb.process = lambda send: np.zeros((len(send), 1), np.float32)
        return player

    def install(self, player, descriptor=None, gain=1, data=None):
        if data is None:
            data = np.ones((48000, 1), np.float32) * 0.5
        with patch("app.player.sf.read", return_value=(data, 48000)):
            player.schedule_cosound({"1": "one.wav"}, [{"sound_id": 1, "gain": gain}], descriptor or timeline())

    def render(self, player, server_time, frames=128, latency=0.04):
        stream_anchor, local_anchor = player._audio_clock_anchor
        dac = server_time - 1000 + stream_anchor - local_anchor
        timing = SimpleNamespace(currentTime=dac - latency, outputBufferDacTime=dac)
        output = np.empty((frames, 1), np.float32)
        player._audio_callback(output, frames, timing, None)
        return output[:, 0]

    def test_different_start_times_output_latencies_and_device_clock_origins_align(self):
        signal = np.sin(np.arange(48000) * 2 * np.pi * 71 / 48000).astype(np.float32)[:, None] * 0.1
        first, late = self.player(), self.player(anchor=(800, 100))
        self.install(first, timeline(fade=0), data=signal)
        self.render(first, 1030, 480)
        self.install(late, timeline(fade=0), data=signal)
        a = self.render(first, 1030.01, latency=0.01)
        b = self.render(late, 1030.01, latency=0.19)
        np.testing.assert_allclose(a, b, atol=1e-7)

    def test_shared_fade_starts_at_sample_inside_callback(self):
        player = self.player()
        self.install(player, timeline(fade=0))
        out = self.render(player, 1010 - 10 / player.fs, 32)
        np.testing.assert_array_equal(out[:10], 0)
        np.testing.assert_allclose(out[10:], 0.5)

    def test_midfade_update_keeps_old_envelope_until_boundary(self):
        player = self.player()
        self.install(player)
        self.install(player, timeline("two", 1014, [{"sound_id": 1, "gain": 0.5}]), gain=0)
        self.assertAlmostEqual(float(self.render(player, 1013)[0]), 0.5 * 3 / 8, places=6)
        self.assertAlmostEqual(float(self.render(player, 1014)[0]), 0.25, places=6)
        self.assertAlmostEqual(float(self.render(player, 1018)[0]), 0.125, places=6)
        np.testing.assert_array_equal(self.render(player, 1023), 0)
        self.assertEqual(player.active_tracks, {})

    def test_late_join_enters_current_fade_and_pending_join_waits_deadline(self):
        late = self.player()
        self.install(late, timeline("two", 1014, [{"sound_id": 1, "gain": 0.5}]), gain=0)
        np.testing.assert_array_equal(self.render(late, 1013), 0)
        self.assertAlmostEqual(float(self.render(late, 1018)[0]), 0.125, places=6)

    def test_initial_clock_lock_waits_without_advancing_local_audio(self):
        player = self.player()
        self.install(player, timeline(fade=0))
        player.clock.server_time = lambda value=None: None
        np.testing.assert_array_equal(self.render(player, 1012), 0)
        self.assertNotIn("sync_ptr", player.active_tracks["one.wav"])
        player.clock.server_time = lambda value=None: 1000 + (value or 0)
        np.testing.assert_allclose(self.render(player, 1013), 0.5)

    def test_unsupported_output_timing_is_reported_and_does_not_free_run(self):
        player = self.player()
        self.install(player)
        out = np.ones((16, 1), np.float32)
        player._audio_callback(out, 16, SimpleNamespace(currentTime=0, outputBufferDacTime=0), None)
        np.testing.assert_array_equal(out, 0)
        self.assertFalse(player._dac_timing_available)

    def test_no_clock_or_output_timing_does_not_accumulate_revisions(self):
        for clock_ready in (False, True):
            player = self.player()
            player.clock.ready = clock_ready
            player._dac_timing_available = False
            for revision in range(50):
                self.install(player, timeline(str(revision), 1010 + revision))
            self.assertEqual(len(player._sync_plans), 1)
            self.assertEqual(len(player.active_tracks), 1)

    def test_python_callback_delay_does_not_move_hardware_deadline(self):
        player = self.player(anchor=(500, 40))
        with patch("app.player.monotonic", return_value=99999):
            got = player._server_output_time(SimpleNamespace(currentTime=500.02, outputBufferDacTime=500.1))
        self.assertAlmostEqual(got, 1040.1)

    def test_output_clock_bridge_rejects_scheduler_delayed_measurement(self):
        player = self.player(anchor=(500, 40))
        player.stream.time = 700
        with patch("app.player.monotonic", side_effect=[100, 100.02]):
            player._capture_audio_clock()
        self.assertEqual(player._audio_clock_anchor, (500, 40))
        with patch("app.player.monotonic", side_effect=[100, 100.00002]):
            player._capture_audio_clock()
        self.assertEqual(player._audio_clock_anchor, (700, 100.00001))

    def test_vote_chimes_use_same_note_and_sample_deadline(self):
        first, second = self.player(), self.player(anchor=(600, 100))
        first._vote_chime_degree = 5
        second._vote_chime_degree = 1
        for player in (first, second):
            player.play_vote_chime(1, play_at=1012, vote_id=83)
        a = self.render(first, 1012 - 10 / first.fs, 256, latency=0.1)
        b = self.render(second, 1012 - 10 / second.fs, 256, latency=0.2)
        np.testing.assert_array_equal(a[:10], 0)
        np.testing.assert_allclose(a, b, atol=1e-7)
        self.assertGreater(float(np.max(np.abs(a))), 0)

    def test_failed_new_asset_leaves_playing_timeline_untouched(self):
        player = self.player()
        self.install(player)
        with patch("app.player.sf.read", side_effect=ValueError("bad audio")):
            with self.assertRaises(ValueError):
                player.schedule_cosound({"2": "bad.wav"}, [{"sound_id": 2, "gain": 1}], timeline("two", 1020))
        self.assertEqual(player._sync_plans[-1].revision, "one")
        self.assertEqual(set(player.active_tracks), {"one.wav"})

    def test_old_snapshots_and_repeated_polls_do_not_restart_or_reload(self):
        player = self.player()
        self.install(player, timeline("latest", 1020))
        with patch("app.player.sf.read") as read:
            player.schedule_cosound({"1": "one.wav"}, [{"sound_id": 1, "gain": 1}], timeline("latest", 1020))
            player.schedule_cosound({"1": "one.wav"}, [{"sound_id": 1, "gain": 1}], timeline("old", 1015))
        read.assert_not_called()
        self.assertEqual(len(player._sync_plans), 1)

    def test_legacy_server_downgrade_resumes_local_mixer_safely(self):
        player = self.player()
        self.install(player)
        self.render(player, 1030)
        player.queue_sound("one.wav", 0.7)
        with patch("app.player.sf.read", return_value=(np.ones((480, 1), np.float32), 48000)):
            player.dequeue_cosound()
        self.assertEqual(player._sync_plans, [])
        self.assertTrue(np.isfinite(self.render(player, 1030.01)).all())

    def test_duration_before_resample_is_preserved(self):
        player = self.player(fs=44100)
        self.install(player, data=np.ones((48001, 1), np.float32))
        self.assertEqual(player.active_tracks["one.wav"]["duration"], 48001 / 48000)
        self.assertNotEqual(len(player.active_tracks["one.wav"]["data"]) / 44100, 48001 / 48000)

    def test_deterministic_source_positions_survive_different_process_histories(self):
        first, second = self.player(), self.player()
        first._pos_idx = 25
        second._pos_idx = 2
        self.install(first)
        self.install(second)
        self.assertEqual(first.active_tracks["one.wav"]["azimuth"], second.active_tracks["one.wav"]["azimuth"])


class LoopPhaseTests(unittest.TestCase):
    def test_device_rate_rounding_does_not_accumulate_after_a_day(self):
        duration = 48001 / 48000
        expected_phase = ((86400.25 - 10) % duration) / duration
        for fs in (44100, 48000, 96000):
            length = round(duration * fs)
            data = (np.arange(length) / length).astype(np.float32)[:, None]
            track = {"data": data, "duration": duration}
            chunk = loop_chunk(track, 16, 86400.25, 10, fs)
            self.assertAlmostEqual(float(chunk[0, 0]), expected_phase, places=6)

    def test_independent_dac_drift_is_continuously_corrected(self):
        fs, frames = 48000, 480
        for drift in (-0.0001, 0.0001):
            track = {"data": np.ones((48001, 1), np.float32), "duration": 48001 / fs}
            for block in range(6000):
                when = 100 + block * frames / (fs * (1 + drift))
                loop_chunk(track, frames, when, 10, fs)
            self.assertLess(abs(track["sync_error_ms"]), 0.1)

    def test_large_dropout_rejoins_with_declick_and_no_permanent_lag(self):
        track = {"data": np.arange(48000, dtype=np.float32)[:, None] / 48000, "duration": 1}
        loop_chunk(track, 480, 10, 10, 48000)
        chunk = loop_chunk(track, 480, 10.5, 10, 48000)
        # The old position leads the crossfade, and the new one takes over
        # once the 50 ms fade (five 480-frame blocks) has run.
        self.assertAlmostEqual(float(chunk[0, 0]), 0.01, places=6)
        for block in range(1, 5):
            chunk = loop_chunk(track, 480, 10.5 + block * 0.01, 10, 48000)
        self.assertNotIn("fade_ptr", track)
        chunk = loop_chunk(track, 480, 10.55, 10, 48000)
        self.assertAlmostEqual(float(chunk[0, 0]), 0.55, places=5)
        self.assertLess(abs(track["sync_error_ms"]), 1e-6)

    def test_skipped_device_cycle_catches_up_by_gliding_not_jumping(self):
        fs, frames = 48000, 1024
        track = {"data": np.ones((48000, 1), np.float32), "duration": 1}
        block = frames / fs
        loop_chunk(track, frames, 100, 10, fs)
        corrections = []
        for index in range(2, 800):  # index 1 is the cycle CoreAudio dropped
            loop_chunk(track, frames, 100 + index * block, 10, fs)
            self.assertNotIn("fade_ptr", track)
            corrections.append(track["sync_correction"])
        steps = np.abs(np.diff([0.0] + corrections))
        self.assertLessEqual(max(corrections), MAX_CORRECTION)
        self.assertLessEqual(steps.max(), MAX_CORRECTION * block / CORRECTION_SLEW_SECONDS + 1e-12)
        # Settles without overshooting into a lead it then has to give back.
        self.assertGreaterEqual(min(corrections), 0)
        self.assertLess(abs(track["sync_error_ms"]), 0.01)

    def test_error_below_seek_threshold_is_recovered_in_seconds(self):
        fs, frames = 48000, 480
        track = {"data": np.ones((48000, 1), np.float32), "duration": 1}
        loop_chunk(track, frames, 100, 10, fs)
        track["sync_ptr"] = (track["sync_ptr"] - 0.2 * fs) % 48000  # 200 ms behind
        for index in range(1, 100 * 60):
            loop_chunk(track, frames, 100 + index * frames / fs, 10, fs)
            self.assertNotIn("fade_ptr", track)
        self.assertLess(abs(track["sync_error_ms"]), 0.1)

    def test_invalid_schedule_rejected(self):
        for descriptor in ({}, timeline(fade=-1), timeline(at=float("nan"))):
            with self.assertRaises(ValueError):
                PlaybackPlan.parse(descriptor, [])


if __name__ == "__main__":
    unittest.main()
