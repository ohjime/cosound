"""One persistent playback schedule is shared by every room receiver."""

from copy import deepcopy
from datetime import datetime, timezone
from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.db import connection, transaction
from django.test import RequestFactory, TestCase

from app.api import PlayerTokenAuth, get_player
from core.models import Manager, Player, PlayerProgram, Post, Prediction, User


def prediction(*layers):
    result = Prediction.new()
    for sound_id, gain in layers:
        result.add_layer(sound_id, gain)
    return result


def instant(seconds):
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


class PlaybackSyncTests(TestCase):
    def setUp(self):
        self.publish = patch("core.player_events.publish_player_changes").start()
        self.addCleanup(patch.stopall)
        self.user = User.objects.create_user(username="sync-manager")
        self.manager = Manager.objects.create(user=self.user, name="Manager")
        with patch("core.models.timezone.now", return_value=instant(1000)):
            self.player = Player.objects.create(
                manager=self.manager, name="Room", playing=prediction((11, 1.0)),
            )

    def test_initial_schedule_and_independent_receiver_snapshots_match(self):
        timeline = self.player.playback_sync
        self.assertEqual(timeline["version"], 1)
        self.assertEqual(timeline["epoch"], 1002)
        self.assertEqual(timeline["effective_at"], 1002)
        self.assertEqual(timeline["fade_seconds"], 8)
        self.assertEqual(timeline["previous_layers"], [])
        auth = PlayerTokenAuth()
        snapshots = []
        for _ in range(2):
            request = RequestFactory().get("/api/player")
            request.auth = auth.authenticate(request, self.player.token)
            snapshots.append(get_player(request)["playback_sync"])
        self.assertEqual(snapshots, [timeline, timeline])
        other = Player.objects.create(manager=self.manager, name="Separate room")
        self.assertNotEqual(other.token, self.player.token)
        self.assertNotEqual(other.playback_sync["revision"], timeline["revision"])

    def test_metadata_same_mix_and_layer_reordering_keep_timeline(self):
        self.player.update(prediction((11, 0.5), (12, 0.8)))
        original = deepcopy(self.player.playback_sync)
        self.player.update(prediction((12, 0.8), (11, 0.5)))
        self.player.name = "Renamed room"
        self.player.save(update_fields=["name"])
        self.player.save()
        self.player.refresh_from_db()
        self.assertEqual(self.player.playback_sync, original)

    def test_interrupted_fades_include_still_audible_removed_layers(self):
        first = self.player.playback_sync["revision"]
        with patch("core.models.timezone.now", return_value=instant(1004)):
            self.player.update(prediction((12, 0.8)))
        self.assertNotEqual(self.player.playback_sync["revision"], first)
        self.assertEqual(self.player.playback_sync["epoch"], 1002)
        self.assertEqual(self.player.playback_sync["effective_at"], 1006)
        self.assertEqual(self.player.playback_sync["previous_layers"], [
            {"sound_id": 11, "gain": 0.5},
        ])
        with patch("core.models.timezone.now", return_value=instant(1008)):
            self.player.update(prediction())
        self.player.refresh_from_db()
        self.assertTrue(self.player.sleeping)
        self.assertEqual(self.player.playback_sync["previous_layers"], [
            {"sound_id": 11, "gain": 0.25}, {"sound_id": 12, "gain": 0.4},
        ])

    def test_program_change_schedules_new_revision_with_same_epoch(self):
        old = deepcopy(self.player.playback_sync)
        self.player.program = PlayerProgram.objects.create(
            post=Post.objects.create(title="Replacement", composer=self.user),
        )
        with patch("core.models.timezone.now", return_value=instant(1020)):
            self.player.save(update_fields=["program"])
        self.player.refresh_from_db()
        self.assertEqual(self.player.playback_sync["epoch"], old["epoch"])
        self.assertEqual(self.player.playback_sync["effective_at"], 1022)
        self.assertNotEqual(self.player.playback_sync["revision"], old["revision"])
        self.assertEqual(self.player.playback_sync["previous_layers"], [
            {"sound_id": 11, "gain": 1.0},
        ])

    def test_next_update_reads_committed_timeline_not_stale_instance(self):
        stale = Player.objects.get(pk=self.player.pk)
        with patch("core.models.timezone.now", return_value=instant(1004)):
            self.player.update(prediction((12, 0.8)))
        with patch("core.models.timezone.now", return_value=instant(1008)):
            stale.update(prediction())
        self.assertEqual(stale.playback_sync["previous_layers"], [
            {"sound_id": 11, "gain": 0.25}, {"sound_id": 12, "gain": 0.4},
        ])

    def test_prediction_and_timeline_rollback_together(self):
        original = deepcopy(self.player.playback_sync)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.player.update(prediction((12, 0.8)))
                raise RuntimeError("rollback")
        self.player.refresh_from_db()
        self.assertEqual(self.player.playback_sync, original)
        self.assertEqual(self.player.playing.layers[0].sound_id, 11)

    def test_backfill_assigns_distinct_revisions_without_changing_prediction(self):
        other = Player.objects.create(manager=self.manager, name="Other room")
        Player.objects.update(playback_sync={})
        migration = import_module("core.migrations.0017_player_playback_sync")
        with patch.object(migration.timezone, "now", return_value=instant(2000)):
            with connection.schema_editor() as editor:
                migration.initialize_playback_timelines(apps, editor)
        self.player.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.player.playback_sync["epoch"], 2002)
        self.assertEqual(other.playback_sync["epoch"], 2002)
        self.assertNotEqual(self.player.playback_sync["revision"], other.playback_sync["revision"])
        self.assertEqual(self.player.playing.layers[0].sound_id, 11)
