import io
import json
import os
import tempfile
import threading
import unittest
from collections import deque
from unittest.mock import Mock, patch

import numpy as np
import soundfile as sf

from app import client
from app.chime import (
    VOTE_CHIME_MAX_RATIO,
    VOTE_CHIME_DOWNVOTE_DEGREES,
    VOTE_CHIME_OUTPUT_CEILING,
    VOTE_CHIME_PEAK,
    VOTE_CHIME_RMS_FLOOR,
    VOTE_CHIME_RMS_SECONDS,
    VOTE_CHIME_ROOT_HZ,
    VOTE_CHIME_SCALE,
    VOTE_CHIME_UPVOTE_DEGREES,
    chime_loudness,
    load_vote_chime,
    vote_chime,
    vote_chime_scale,
)
from app.live import _receive_changes
from app.player import SoundDevicePlayer, _levels_of


class VoteEventsTests(unittest.IsolatedAsyncioTestCase):
    async def test_votes_chime_once_across_connections_without_refreshing_the_mix(self):
        class Socket:
            async def recv(self):
                return json.dumps({"type": "player.ready", "schema_version": 1})

            async def __aiter__(self):
                for vote_id in (1, 1, True, None, -1, "2", 2):
                    yield json.dumps({"type": "player.vote_received", "schema_version": 1, "vote_id": vote_id})

        chime, refresh, status = Mock(), Mock(), Mock()
        seen = deque(maxlen=512)
        for _ in range(2):
            await _receive_changes(Socket(), refresh, status, chime, seen)
        self.assertEqual(chime.call_count, 2)
        self.assertEqual(refresh.call_count, 2)  # Ready only, never a vote.

    async def test_vote_polarity_is_forwarded_when_present(self):
        class Socket:
            async def recv(self):
                return json.dumps({"type": "player.ready", "schema_version": 1})

            async def __aiter__(self):
                for vote_id, pleasant in ((1, 0), (2, 1), (3, None)):
                    yield json.dumps({
                        "type": "player.vote_received", "schema_version": 1,
                        "vote_id": vote_id, "pleasant": pleasant,
                    })

        chime = Mock()
        await _receive_changes(Socket(), Mock(), Mock(), chime)
        self.assertEqual(chime.call_args_list, [unittest.mock.call(0), unittest.mock.call(1), unittest.mock.call()])


class ChimeAudioTests(unittest.TestCase):
    def player(self):
        player = SoundDevicePlayer.__new__(SoundDevicePlayer)
        player.lock = threading.Lock()
        player.channels = 2
        player.master_gain = 0.7
        player.muted = False
        player.active_tracks = {}
        player.pending_queue = {"current-mix.wav": 0.5}
        player.fs = 48000
        player._default_vote_chime = vote_chime_scale(48000)
        player._vote_chime = player._default_vote_chime
        player._vote_chime_positions = []
        player._vote_chime_degree = -1
        player._vote_chime_peak, player._vote_chime_loudness = _levels_of(
            player._vote_chime, player.fs
        )
        player._vote_chime_volume = 0.5
        player._mix_rms = 0.0
        player.renderer = Mock()
        player.renderer.render.side_effect = lambda sources, frames: (np.zeros((frames, 2), np.float32), np.zeros((frames, 2), np.float32))
        player.reverb = Mock()
        player.reverb.process.side_effect = lambda send: np.zeros_like(send)
        return player

    def test_one_shot_finishes_without_altering_mix_or_looping(self):
        player = self.player()
        player.play_vote_chime()
        frames = max(len(voice) for voice in player._vote_chime) + 32
        output = np.empty((frames, 2), np.float32)
        player._audio_callback(output, frames, None, None)
        self.assertGreater(np.max(np.abs(output)), 0.01)
        self.assertTrue(np.isfinite(output).all())
        self.assertEqual(player.pending_queue, {"current-mix.wav": 0.5})
        self.assertEqual(player.active_tracks, {})
        player._audio_callback(output, frames, None, None)
        np.testing.assert_array_equal(output, 0)

    def test_mute_and_zero_volume_apply_to_chime_and_consume_it(self):
        for muted, gain in ((True, 0.7), (False, 0.0)):
            player = self.player()
            player.muted, player.master_gain = muted, gain
            player.play_vote_chime()
            output = np.empty((24000, 2), np.float32)
            player._audio_callback(output, 24000, None, None)
            np.testing.assert_array_equal(output, 0)
            self.assertEqual(player._vote_chime_positions, [])

    def test_bursts_are_bounded_and_new_taps_start_immediately(self):
        player = self.player()
        for _ in range(100):
            player.play_vote_chime()
        self.assertEqual(len(player._vote_chime_positions), 8)
        self.assertEqual([position for _, position in player._vote_chime_positions], [0] * 8)

    def test_custom_chime_swap_is_atomic_and_reset_restores_fallback(self):
        player = self.player()
        fallback = player._default_vote_chime
        custom = np.full(32, 0.05, dtype=np.float32)
        player._vote_chime_positions = [(5, 100)]

        player.set_vote_chime(custom)
        self.assertEqual(len(player._vote_chime), len(VOTE_CHIME_SCALE))
        np.testing.assert_array_equal(player._vote_chime[5], custom)
        self.assertEqual(player._vote_chime_positions, [])

        # The installed root must not alias the caller's array, which it is
        # free to reuse while the audio thread is reading.
        custom[:] = 0.5
        self.assertTrue(np.all(player._vote_chime[5] == np.float32(0.05)))

        player.set_vote_chime()
        self.assertIs(player._vote_chime, fallback)
        self.assertEqual(player._vote_chime_positions, [])


class ChimeLevelTests(unittest.TestCase):
    """The one-shot is levelled against the mix it interrupts, not full scale."""

    def player(self, mix_level=0.0):
        player = ChimeAudioTests.player(self)
        # A steady dry signal stands in for the soundscape, so the measured RMS
        # is exactly `mix_level` and the chime has a known thing to sit against.
        player.renderer.render.side_effect = lambda sources, frames: (
            np.full((frames, 2), mix_level, np.float32),
            np.zeros((frames, 2), np.float32),
        )
        player.master_gain = 1.0
        player._mix_rms = mix_level
        return player

    def chime_only(self, player, frames=24000):
        """The acknowledgement alone, as one channel receives it.

        Rendering the same block with and without a vote isolates the chime:
        nothing else in this callback carries state between the two.
        """
        quiet = np.empty((frames, 2), np.float32)
        player._audio_callback(quiet, frames, None, None)
        player.play_vote_chime()
        loud = np.empty((frames, 2), np.float32)
        player._audio_callback(loud, frames, None, None)
        return (loud - quiet)[:, 0]

    def chime_loudness(self, player, frames=24000):
        """How loud the acknowledgement sounds, as short-term RMS."""
        return chime_loudness(self.chime_only(player, frames), player.fs)

    def degree_share(self, player):
        """How the sounding degree compares with the one the scale is set by.

        The whole scale is levelled by its loudest degree so the balance between
        degrees survives, which means the degree actually sounding may sit a
        little under the target.  That is the design, so the expected level is
        scaled by the same ratio rather than the tolerance being widened.
        """
        sounding = chime_loudness(player._vote_chime[player._vote_chime_degree], player.fs)
        return sounding / player._vote_chime_loudness

    def assertLevel(self, measured, target):
        self.assertAlmostEqual(measured, target, delta=0.01 * target)

    def test_volume_a_quarter_puts_the_chime_level_with_the_soundscape(self):
        # The setting is a loudness ratio, so the two are directly comparable:
        # a quarter of the range is parity, and the rest is headroom above it.
        for mix_level in (0.1, 0.2):
            with self.subTest(mix_level=mix_level):
                player = self.player(mix_level)
                player._vote_chime_volume = 1.0 / VOTE_CHIME_MAX_RATIO
                self.assertLevel(
                    self.chime_loudness(player),
                    mix_level * self.degree_share(player),
                )

    def test_loudness_follows_the_volume_setting_up_to_the_full_ratio(self):
        # Mixes loud enough to clear the silent-room floor and quiet enough
        # that the full ratio still fits under the output ceiling; both of those
        # bounds have tests of their own below.
        for mix_level in (0.06, 0.07):
            for volume in (0.1, 0.5, 1.0):
                with self.subTest(mix_level=mix_level, volume=volume):
                    player = self.player(mix_level)
                    player._vote_chime_volume = volume
                    self.assertLevel(
                        self.chime_loudness(player),
                        volume
                        * VOTE_CHIME_MAX_RATIO
                        * mix_level
                        * self.degree_share(player),
                    )

    def test_full_volume_carries_well_over_a_busy_mix(self):
        # The regression this replaces: a fixed ceiling held the chime under the
        # soundscape even at maximum, so 1.0 was never actually loud.  On a mix
        # this dense the output ceiling is what limits it, and it still lands
        # comfortably above the soundscape rather than beneath it.
        player = self.player(0.1)
        player._vote_chime_volume = 1.0
        self.assertGreater(self.chime_loudness(player), 2.5 * 0.1)

    def test_a_quiet_room_still_gets_an_audible_acknowledgement(self):
        # Scaling by the mix alone would acknowledge a vote with silence in a
        # sleeping or between-transitions room, so a floor holds the reference.
        player = self.player(0.0)
        player._vote_chime_volume = 1.0 / VOTE_CHIME_MAX_RATIO
        self.assertLevel(
            self.chime_loudness(player),
            VOTE_CHIME_RMS_FLOOR * self.degree_share(player),
        )

    def test_one_acknowledgement_never_reaches_the_clipper_on_its_own(self):
        player = self.player(0.9)
        player._vote_chime_volume = 1.0
        peak = float(np.max(np.abs(self.chime_only(player))))
        self.assertLessEqual(peak, VOTE_CHIME_OUTPUT_CEILING)
        self.assertGreater(peak, 0.0)

    def test_zero_volume_silences_the_chime_but_still_consumes_it(self):
        player = self.player(0.2)
        player._vote_chime_volume = 0.0
        self.assertEqual(float(np.max(np.abs(self.chime_only(player)))), 0.0)
        self.assertEqual(player._vote_chime_positions, [])

    def test_a_quieter_upload_is_raised_to_the_same_level_as_any_other(self):
        # An upload arrives at whatever level it was stored at.  Levelling by
        # how loud it actually is, rather than assuming a fixed level, is what
        # lets a quiet one-shot still meet the setting.
        player = self.player(0.1)
        player._vote_chime_volume = 0.5
        # Windowed rather than square-edged: a hard-edged one-shot rings when
        # the scale's other degrees are resampled, which is the degree
        # levelling above rather than the behaviour this test is about.
        # Half a second, comfortably longer than the measurement window, so
        # the level it is installed at and the level measured off the output
        # are describing the same thing.
        t = np.arange(round(player.fs * 0.5)) / round(player.fs * 0.5)
        quiet_upload = 0.001 * np.sin(np.pi * t) * np.sin(2 * np.pi * 440 * t)
        player.set_vote_chime(quiet_upload.astype(np.float32))
        self.assertLevel(
            self.chime_loudness(player, player.fs),
            0.5 * VOTE_CHIME_MAX_RATIO * 0.1 * self.degree_share(player),
        )

    def test_the_reference_averages_the_mix_instead_of_chasing_a_transient(self):
        player = self.player(0.0)
        player._vote_chime_volume = 1.0
        frames = round(player.fs * VOTE_CHIME_RMS_SECONDS)
        loud = np.empty((frames, 2), np.float32)

        # One loud block moves the reference part of the way, not all of it...
        player.renderer.render.side_effect = lambda sources, frames: (
            np.full((frames, 2), 0.4, np.float32),
            np.zeros((frames, 2), np.float32),
        )
        player._audio_callback(loud, frames, None, None)
        self.assertLess(player._mix_rms, 0.4)
        self.assertGreater(player._mix_rms, VOTE_CHIME_RMS_FLOOR)

        # ...and a mix that stays loud is eventually followed in full.
        for _ in range(8):
            player._audio_callback(loud, frames, None, None)
        self.assertAlmostEqual(player._mix_rms, 0.4, places=3)

    def test_volume_is_clamped_to_the_documented_range_and_rejects_nonsense(self):
        player = self.player()
        for requested, expected in ((-1.0, 0.0), (0.25, 0.25), (4.0, 1.0)):
            player.set_vote_chime_volume(requested)
            self.assertEqual(player._vote_chime_volume, expected)
        with self.assertRaises(ValueError):
            player.set_vote_chime_volume(float("nan"))


class ChimeScaleTests(unittest.TestCase):
    @staticmethod
    def dominant_hz(samples, sample_rate):
        spectrum = np.abs(np.fft.rfft(samples.astype(np.float64)))
        return float(np.fft.rfftfreq(len(samples), 1.0 / sample_rate)[np.argmax(spectrum)])

    def test_scale_is_consonant_under_overlap(self):
        # Vote chimes are mixed together, so no two degrees may form a minor
        # second or a tritone. That property is the reason for this scale.
        for low in VOTE_CHIME_SCALE:
            for high in VOTE_CHIME_SCALE:
                interval = abs(high - low) % 12
                self.assertNotIn(interval, (1, 6), f"{low} against {high}")

    def test_each_degree_sounds_its_own_pitch(self):
        sample_rate = 48_000
        scale = vote_chime_scale(sample_rate)

        self.assertEqual(len(scale), len(VOTE_CHIME_SCALE))
        for voice, semitones in zip(scale, VOTE_CHIME_SCALE):
            expected = VOTE_CHIME_ROOT_HZ * 2.0 ** (semitones / 12.0)
            self.assertAlmostEqual(
                self.dominant_hz(voice, sample_rate) / expected, 1.0, places=1
            )
        # The same pentatonic degree is exactly an octave higher for upvotes.
        self.assertAlmostEqual(
            self.dominant_hz(scale[5], sample_rate)
            / self.dominant_hz(scale[0], sample_rate),
            2.0,
            places=1,
        )

    def test_votes_pick_random_consonant_notes_without_immediate_repeats(self):
        player = ChimeAudioTests().player()
        with patch("app.player.random.choice", side_effect=lambda choices: choices[-1]) as choose:
            player.play_vote_chime(0)
            down = player._vote_chime_positions[-1][0]
            player.play_vote_chime(0)
            next_down = player._vote_chime_positions[-1][0]
            player.play_vote_chime(1)
            up = player._vote_chime_positions[-1][0]
            player.play_vote_chime()
            unknown = player._vote_chime_positions[-1][0]
        self.assertIn(down, VOTE_CHIME_DOWNVOTE_DEGREES)
        self.assertIn(next_down, VOTE_CHIME_DOWNVOTE_DEGREES)
        self.assertNotEqual(down, next_down)
        self.assertIn(up, VOTE_CHIME_UPVOTE_DEGREES)
        self.assertIn(unknown, range(len(VOTE_CHIME_SCALE)))
        self.assertEqual(choose.call_count, 4)

    def test_an_upload_is_repitched_onto_the_same_scale(self):
        sample_rate = 48_000
        seconds = 0.25
        t = np.arange(round(sample_rate * seconds)) / sample_rate
        upload = (0.1 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)

        scale = vote_chime_scale(sample_rate, upload)

        self.assertEqual(len(scale), len(VOTE_CHIME_SCALE))
        for voice, semitones in zip(scale, VOTE_CHIME_SCALE):
            ratio = 2.0 ** (semitones / 12.0)
            self.assertAlmostEqual(
                self.dominant_hz(voice, sample_rate) / (440.0 * ratio), 1.0, places=1
            )
            self.assertLessEqual(len(voice), sample_rate * 5)
            # Resampling rings above the source peak; the ceiling is re-applied
            # so eight overlapping chimes keep the headroom the root had.
            self.assertLessEqual(float(np.max(np.abs(voice))), VOTE_CHIME_PEAK + 1e-6)
            self.assertEqual(voice.dtype, np.float32)
            self.assertTrue(voice.flags.c_contiguous)

    def test_long_upload_pitched_down_ends_with_a_fade(self):
        sample_rate = 8_000
        t = np.arange(sample_rate * 5) / sample_rate
        upload = (0.1 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        low = vote_chime_scale(sample_rate, upload)[0]
        self.assertEqual(len(low), sample_rate * 5)
        self.assertAlmostEqual(float(low[-1]), 0.0, places=6)


class UploadedChimeTests(unittest.TestCase):
    def test_decode_downmix_resample_and_peak_cap(self):
        source_rate = 24_000
        frames = source_rate // 10
        stereo = np.column_stack(
            (
                np.full(frames, 0.8, dtype=np.float32),
                np.full(frames, 0.4, dtype=np.float32),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "chime.wav")
            sf.write(path, stereo, source_rate, subtype="FLOAT")
            prepared = load_vote_chime(path, 48_000)

        self.assertEqual(prepared.dtype, np.float32)
        self.assertEqual(prepared.ndim, 1)
        self.assertEqual(len(prepared), frames * 2)
        self.assertTrue(prepared.flags.c_contiguous)
        self.assertAlmostEqual(float(np.max(np.abs(prepared))), VOTE_CHIME_PEAK, places=5)

    def test_empty_or_overlong_upload_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            silent = os.path.join(directory, "silent.wav")
            long = os.path.join(directory, "long.wav")
            sf.write(silent, np.zeros(100, dtype=np.float32), 48_000)
            sf.write(long, np.ones(48_000 * 6, dtype=np.float32), 48_000)
            with self.assertRaisesRegex(ValueError, "silent"):
                load_vote_chime(silent, 48_000)
            with self.assertRaisesRegex(ValueError, "at most 5 seconds"):
                load_vote_chime(long, 48_000)


class VoteChimeCacheTests(unittest.TestCase):
    class Response(io.BytesIO):
        def __init__(self, content, headers=None):
            super().__init__(content)
            self.headers = headers or {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def test_cache_is_version_addressed_atomic_and_ignores_changed_signed_url(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            client, "VOTE_CHIME_CACHE_DIR", directory
        ), patch.object(
            client.urllib.request,
            "urlopen",
            return_value=self.Response(b"audio-bytes"),
        ) as fetch:
            first = client.get_vote_chime("sounds/player/one.wav", "https://media/a?sig=1")
            second = client.get_vote_chime("sounds/player/one.wav", "https://media/a?sig=2")

            self.assertEqual(first, second)
            with open(first, "rb") as cached:
                self.assertEqual(cached.read(), b"audio-bytes")
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(os.listdir(directory), [os.path.basename(first)])
            request = fetch.call_args.args[0]
            self.assertIsNone(request.get_header("X-api-key"))
            self.assertEqual(fetch.call_args.kwargs["timeout"], client.HTTP_TIMEOUT)

    def test_failed_download_leaves_no_partial_cache_entry(self):
        oversized = b"x" * (client.VOTE_CHIME_DOWNLOAD_LIMIT + 1)
        with tempfile.TemporaryDirectory() as directory, patch.object(
            client, "VOTE_CHIME_CACHE_DIR", directory
        ), patch.object(
            client.urllib.request,
            "urlopen",
            return_value=self.Response(oversized),
        ):
            with self.assertRaisesRegex(ValueError, "too large"):
                client.get_vote_chime("version-1", "https://media/chime")
            self.assertEqual(os.listdir(directory), [])

    def test_non_http_url_is_rejected_before_network_access(self):
        with patch.object(client.urllib.request, "urlopen") as fetch:
            with self.assertRaisesRegex(ValueError, "HTTP or HTTPS"):
                client.get_vote_chime("version-1", "file:///etc/passwd")
        fetch.assert_not_called()

    def test_pruning_is_bounded_keeps_current_and_ignores_directories(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            client, "VOTE_CHIME_CACHE_DIR", directory
        ):
            current = client._vote_chime_cache_path("current")
            with open(current, "wb") as cached:
                cached.write(b"current")
            os.utime(current, ns=(1, 1))
            for index in range(client.VOTE_CHIME_CACHE_LIMIT + 2):
                stale = client._vote_chime_cache_path(f"stale-{index}")
                with open(stale, "wb") as cached:
                    cached.write(b"stale")
                os.utime(stale, ns=(index + 2, index + 2))
            nested = os.path.join(directory, "keep-directory")
            os.mkdir(nested)

            client.prune_vote_chimes("current")
            remaining = set(os.listdir(directory))
            self.assertIn(os.path.basename(current), remaining)
            self.assertIn("keep-directory", remaining)
            self.assertEqual(len(remaining), client.VOTE_CHIME_CACHE_LIMIT + 1)

            client.prune_vote_chimes()
            self.assertEqual(
                set(os.listdir(directory)),
                remaining,
            )
