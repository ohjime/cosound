import math
import random
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from taggit.models import Tag

from core.management.commands.refresh import (
    Command,
    SCHEDULER_TICK_SECONDS,
    _get_predictor,
    _refresh_is_due,
    _task_is_in_flight,
)
from core.models import (
    Post,
    AlgorithmDecision,
    Artist,
    Cosound,
    Listener,
    PlayerProgram,
    Manager,
    PlaybackExposure,
    Player,
    Prediction,
    Sound,
    User,
)
from core.predict import (
    Algorithm,
    PREDICTION_RETRY,
    _predict_for_player,
    stable_preference_predictor,
)
from core.prediction import (
    ListenerEvidence,
    Mix,
    MixLayer,
    SelectionConfig,
    SoundEvidence,
    VoteEvidence,
    enumerate_candidates,
    select_mix,
)
from core.prediction.live import run_stable_prediction
from vote.models import Vote


class RefreshSchedulerTests(SimpleTestCase):
    def test_stable_predictor_is_the_configured_default(self):
        self.assertIs(_get_predictor(), stable_preference_predictor)

    @override_settings(COSOUND_CORE_PREDICTOR="core.predict.random_predictor")
    def test_can_roll_back_to_the_earlier_predictor_by_setting(self):
        from core.predict import random_predictor

        self.assertIs(_get_predictor(), random_predictor)

    @override_settings(COSOUND_CORE_PREDICTOR="core.predict.does_not_exist")
    def test_invalid_predictor_path_fails_instead_of_silently_using_random(self):
        with self.assertRaisesMessage(
            CommandError,
            "Could not import COSOUND_CORE_PREDICTOR='core.predict.does_not_exist'",
        ):
            _get_predictor()

    @patch(
        "core.management.commands.refresh.time.sleep",
        side_effect=KeyboardInterrupt,
    )
    @patch("core.management.commands.refresh.Player.objects.filter")
    @patch("core.management.commands.refresh._get_predictor")
    def test_waits_one_second_between_scheduler_ticks(
        self,
        _get_predictor,
        players,
        sleep,
    ):
        players.return_value.select_related.return_value = []

        with self.assertRaises(SystemExit) as stopped:
            Command().handle()

        self.assertEqual(stopped.exception.code, 0)
        self.assertEqual(SCHEDULER_TICK_SECONDS, 1)
        players.assert_called_once_with(sleeping=False)
        players.return_value.select_related.assert_called_once_with("program")
        sleep.assert_called_once_with(1)

    @patch(
        "core.management.commands.refresh.time.sleep",
        side_effect=KeyboardInterrupt,
    )
    @patch("core.management.commands.refresh.Player.objects.filter")
    @patch("core.management.commands.refresh._get_predictor")
    def test_only_awake_players_are_enqueued(
        self,
        get_predictor,
        players,
        _sleep,
    ):
        awake = SimpleNamespace(
            pk=7,
            name="Awake room",
            program=SimpleNamespace(algorithm_refresh_interval_seconds=30),
        )
        players.return_value.select_related.return_value = [awake]

        with self.assertRaises(SystemExit):
            Command().handle()

        players.assert_called_once_with(sleeping=False)
        players.return_value.select_related.assert_called_once_with("program")
        get_predictor.return_value.enqueue.assert_called_once_with(player_id=awake.pk)

    @patch(
        "core.management.commands.refresh.time.sleep",
        side_effect=[None] * 10 + [KeyboardInterrupt],
    )
    @patch(
        "core.management.commands.refresh.time.monotonic",
        side_effect=list(range(11)),
    )
    @patch("core.management.commands.refresh.Player.objects.filter")
    @patch("core.management.commands.refresh._get_predictor")
    def test_each_player_is_enqueued_on_its_own_cadence(
        self,
        get_predictor,
        players,
        _monotonic,
        sleep,
    ):
        every_five_seconds = SimpleNamespace(
            pk=7,
            name="Quick room",
            program=SimpleNamespace(algorithm_refresh_interval_seconds=5),
        )
        every_ten_seconds = SimpleNamespace(
            pk=8,
            name="Slow room",
            program=SimpleNamespace(algorithm_refresh_interval_seconds=10),
        )
        players.return_value.select_related.return_value = [
            every_five_seconds,
            every_ten_seconds,
        ]

        with self.assertRaises(SystemExit):
            Command().handle()

        self.assertEqual(
            get_predictor.return_value.enqueue.call_args_list,
            [
                call(player_id=every_five_seconds.pk),
                call(player_id=every_ten_seconds.pk),
                call(player_id=every_five_seconds.pk),
                call(player_id=every_five_seconds.pk),
                call(player_id=every_ten_seconds.pk),
            ],
        )
        self.assertEqual(players.call_count, 11)
        players.assert_called_with(sleeping=False)
        self.assertEqual(
            players.return_value.select_related.call_args_list,
            [call("program")] * 11,
        )
        self.assertEqual(sleep.call_args_list, [call(1)] * 11)

    def test_a_changed_program_interval_is_used_without_restarting(self):
        player = SimpleNamespace(
            pk=7,
            program=SimpleNamespace(algorithm_refresh_interval_seconds=30),
        )
        last_enqueued_at = {player.pk: 0.0}

        self.assertFalse(_refresh_is_due(player, last_enqueued_at, 10.0))
        player.program.algorithm_refresh_interval_seconds = 5
        self.assertTrue(_refresh_is_due(player, last_enqueued_at, 10.0))

    def test_an_unfinished_prediction_prevents_overlapping_enqueues(self):
        task_result = Mock(is_finished=False)

        self.assertTrue(_task_is_in_flight(task_result))
        task_result.refresh.assert_called_once_with()

        task_result.is_finished = True
        self.assertFalse(_task_is_in_flight(task_result))


class ListenerTestPointAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin-password",
        )
        cls.listener_user = User.objects.create_user(
            username="listener",
            email="listener@example.com",
        )
        cls.listener = Listener.objects.create(user=cls.listener_user)

        cls.ambient_sound = cls.create_sound("Ambient one")
        cls.second_ambient_sound = cls.create_sound("Ambient two")
        cls.old_sound = cls.create_sound("Old favourite")
        cls.ambient_sound.tags.add("ambient")
        cls.second_ambient_sound.tags.add("ambient", "field")
        cls.old_sound.tags.add("legacy")

        cls.ambient_tag = Tag.objects.get(name="ambient")
        cls.empty_tag = Tag.objects.create(name="unused", slug="unused")

        cls.manager = Manager.objects.create(user=cls.admin, name="Test manager")
        cls.player = Player.objects.create(manager=cls.manager, name="Test player")
        cls.cosound = Cosound.objects.create(hashset="hashset", hashid="hashid")
        cls.vote = Vote.objects.create(
            voter=cls.listener,
            player=cls.player,
            cosound=cls.cosound,
            pleasant=Vote.UPVOTE,
            section="before-action",
        )

    @staticmethod
    def create_sound(title):
        return Sound.objects.create(
            file=f"sounds/{title.lower().replace(' ', '-')}.wav",
            title=title,
            embeddings=[0, 0, 0, 0, 0],
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.change_url = reverse(
            "admin:core_listener_change", args=[self.listener.pk]
        )
        self.action_url = reverse(
            "admin:core_listener_set_test_point", args=[self.listener.pk]
        )

    def test_change_page_shows_test_point_control_with_current_tags(self):
        response = self.client.get(self.change_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Set test point")
        self.assertContains(response, f'value="{self.ambient_tag.pk}"')
        self.assertContains(response, ">ambient</option>")
        self.assertContains(response, f'value="{self.empty_tag.pk}"')
        self.assertContains(response, ">unused</option>")
        self.assertContains(response, f'action="{self.action_url}"')

    def test_action_replaces_collection_and_preserves_votes(self):
        self.listener.collection.add(self.old_sound, self.ambient_sound)

        response = self.client.post(
            self.action_url,
            {"test_point_tag": self.ambient_tag.pk},
        )

        self.assertRedirects(response, self.change_url, fetch_redirect_response=False)
        self.assertSetEqual(
            set(self.listener.collection.all()),
            {self.ambient_sound, self.second_ambient_sound},
        )
        self.vote.refresh_from_db()
        self.assertEqual(self.vote.pleasant, Vote.UPVOTE)
        self.assertEqual(self.vote.section, "before-action")

        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn(
            'Set test point to "ambient" and replaced the collection with 2 sounds.',
            messages,
        )

    def test_tag_without_sounds_clears_collection_and_reports_result(self):
        self.listener.collection.add(self.old_sound, self.ambient_sound)

        response = self.client.post(
            self.action_url,
            {"test_point_tag": self.empty_tag.pk},
        )

        self.assertRedirects(response, self.change_url, fetch_redirect_response=False)
        self.assertFalse(self.listener.collection.exists())
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn(
            'Set test point to "unused". No sounds use this tag, so the collection is now empty.',
            messages,
        )

    def test_invalid_tag_does_not_change_collection(self):
        self.listener.collection.add(self.old_sound)

        response = self.client.post(
            self.action_url,
            {"test_point_tag": "not-a-tag-id"},
        )

        self.assertRedirects(response, self.change_url, fetch_redirect_response=False)
        self.assertSetEqual(set(self.listener.collection.all()), {self.old_sound})
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn(
            "Select a valid tag before setting a test point.",
            messages,
        )

    def test_action_rejects_get_requests(self):
        response = self.client.get(self.action_url)

        self.assertEqual(response.status_code, 405)

    def test_action_requires_listener_change_permission(self):
        viewer = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            is_staff=True,
        )
        viewer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="view_listener",
            )
        )
        self.client.force_login(viewer)
        self.listener.collection.add(self.old_sound)

        response = self.client.post(
            self.action_url,
            {"test_point_tag": self.ambient_tag.pk},
        )

        self.assertEqual(response.status_code, 403)
        self.assertSetEqual(set(self.listener.collection.all()), {self.old_sound})


class PlayerAdminAwakenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="player-admin",
            email="player-admin@example.com",
            password="admin-password",
        )
        cls.manager = Manager.objects.create(user=cls.admin, name="Player manager")
        cls.player = Player.objects.create(manager=cls.manager, name="Garden player")
        cls.sound = Sound.objects.create(
            file="sounds/garden.wav",
            title="Garden birds",
            embeddings=[0, 0, 0, 0, 0],
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def submit_awake_edit(self):
        return self.client.post(
            reverse("admin:core_player_change", args=[self.player.pk]),
            {
                "name": self.player.name,
                "manager": self.manager.pk,
                "post": self.player.program_id,
                "state_refresh_interval_seconds": (
                    self.player.state_refresh_interval_seconds
                ),
            },
        )

    def test_player_editor_delegates_waking_to_algorithm(self):
        self.player.program.collection.add(self.sound)

        with patch("core.predict.Algorithm.awaken", return_value=object()) as awaken:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.submit_awake_edit()

        self.assertEqual(response.status_code, 302)
        awaken.assert_called_once()
        self.assertEqual(awaken.call_args.args[0].pk, self.player.pk)

    def test_player_editor_warns_when_algorithm_cannot_awaken(self):
        with patch("core.predict.Algorithm.awaken", return_value=None) as awaken:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.submit_awake_edit()

        awaken.assert_called_once()
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn(
            "This player stayed asleep because the algorithm could not select a "
            "playable mix.",
            messages,
        )

    def test_player_editor_reports_post_commit_algorithm_failure(self):
        self.player.program.collection.add(self.sound)

        with (
            patch(
                "core.predict.Algorithm.awaken",
                side_effect=RuntimeError("broken algorithm"),
            ) as awaken,
            patch("core.admin.logger.exception") as log_exception,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.submit_awake_edit()

        self.assertEqual(response.status_code, 302)
        awaken.assert_called_once()
        log_exception.assert_called_once()
        messages = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertIn(
            "The player was saved, but its algorithm could not be resumed.",
            messages,
        )


class PredictorTests(TestCase):
    def setUp(self):
        manager_user = User.objects.create_user(
            username="manager",
            email="manager@example.com",
            password="password",
        )
        self.manager = Manager.objects.create(user=manager_user, name="Manager")
        self.player = Player.objects.create(manager=self.manager, name="Player")
        Player.objects.filter(pk=self.player.pk).update(sleeping=False)
        self.player.sleeping = False
        self.cosound = Cosound.objects.create(hashid="vote", hashset="vote")
        self.listener_number = 0

    def make_sound(self, title, *tags):
        sound = Sound.objects.create(
            file=f"sounds/{title}.mp3",
            title=title,
            embeddings=[0.0] * 5,
        )
        sound.tags.add(*tags)
        return sound

    def make_listener(self, *sounds):
        self.listener_number += 1
        number = self.listener_number
        user = User.objects.create_user(
            username=f"listener-{number}",
            email=f"listener-{number}@example.com",
            password="password",
        )
        listener = Listener.objects.create(user=user)
        listener.collection.add(*sounds)
        return listener

    def vote(self, listener, *, player=None, created_at=None, pleasant=Vote.UPVOTE):
        vote = Vote.objects.create(
            voter=listener,
            player=player or self.player,
            cosound=self.cosound,
            pleasant=pleasant,
        )
        if created_at is not None:
            Vote.objects.filter(pk=vote.pk).update(created_at=created_at)
        return vote

    def predict(self):
        with patch.object(Player, "announce"):
            return _predict_for_player(self.player.pk)

    def test_only_voters_from_the_last_five_minutes_are_active(self):
        rock = self.make_sound("rock", "rock")
        jazz = self.make_sound("jazz", "jazz")
        self.player.program.collection.add(rock, jazz)
        recent_listener = self.make_listener(rock)
        stale_listener = self.make_listener(jazz)
        other_player_listener = self.make_listener(jazz)
        other_player = Player.objects.create(
            manager=self.manager,
            name="Other Player",
        )
        now = timezone.now()
        self.vote(recent_listener, created_at=now - timedelta(minutes=4, seconds=59))
        self.vote(stale_listener, created_at=now - timedelta(minutes=5, seconds=1))
        self.vote(other_player_listener, player=other_player)

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertEqual(
            [layer.sound_id for layer in self.player.playing.layers],
            [rock.pk],
        )

    def test_multiple_votes_from_one_listener_produce_one_layer(self):
        sound = self.make_sound("ambient", "ambient")
        self.player.program.collection.add(sound)
        listener = self.make_listener(sound)
        self.vote(listener)
        self.vote(listener, pleasant=Vote.DOWNVOTE)
        self.vote(listener)

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertEqual(len(self.player.playing.layers), 1)
        self.assertEqual(self.player.playing.layers[0].sound_gain, 1.0)

    def test_each_listener_contributes_a_layer_from_their_own_top_tag(self):
        library_rock = self.make_sound("library-rock", "rock")
        library_jazz = self.make_sound("library-jazz", "jazz")
        self.player.program.collection.add(library_rock, library_jazz)
        rock_one = self.make_sound("rock-one", "rock")
        rock_two = self.make_sound("rock-two", "rock")
        jazz_one = self.make_sound("jazz-one", "jazz")
        jazz_two = self.make_sound("jazz-two", "jazz")
        rock_listener = self.make_listener(rock_one, rock_two)
        jazz_listener = self.make_listener(jazz_one, jazz_two)
        self.vote(rock_listener)
        self.vote(jazz_listener)

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertEqual(
            [layer.sound_id for layer in self.player.playing.layers],
            [library_rock.pk, library_jazz.pk],
        )
        self.assertEqual(
            [layer.sound_gain for layer in self.player.playing.layers],
            [1.0, 1.0],
        )

    def test_tied_usable_top_tags_are_selected_randomly(self):
        rock = self.make_sound("library-rock", "rock")
        jazz = self.make_sound("library-jazz", "jazz")
        self.player.program.collection.add(rock, jazz)
        collected = self.make_sound("collected", "rock", "jazz")
        listener = self.make_listener(collected)
        self.vote(listener)
        jazz_tag_id = jazz.tags.get().pk

        def choose_jazz(options):
            if isinstance(options[0], int):
                return jazz_tag_id
            return options[0]

        with patch("core.predict.random.choice", side_effect=choose_jazz) as choice:
            self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertEqual(self.player.playing.layers[0].sound_id, jazz.pk)
        self.assertEqual(choice.call_count, 2)

    def test_uses_a_matching_tag_when_another_tied_top_tag_is_unavailable(self):
        jazz = self.make_sound("library-jazz", "jazz")
        self.player.program.collection.add(jazz)
        collected = self.make_sound("collected", "jazz", "unavailable")
        listener = self.make_listener(collected)
        self.vote(listener)

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertEqual(self.player.playing.layers[0].sound_id, jazz.pk)

    def test_does_not_fall_back_to_a_less_frequent_tag(self):
        jazz = self.make_sound("library-jazz", "jazz")
        self.player.program.collection.add(jazz)
        unavailable_one = self.make_sound("unavailable-one", "unavailable")
        unavailable_two = self.make_sound("unavailable-two", "unavailable")
        collected_jazz = self.make_sound("collected-jazz", "jazz")
        listener = self.make_listener(
            unavailable_one,
            unavailable_two,
            collected_jazz,
        )
        self.vote(listener)

        self.assertEqual(self.predict(), 0)

        self.player.refresh_from_db()
        self.assertEqual(self.player.playing.layers, [])

    def test_selected_sound_is_restricted_to_the_players_library(self):
        library_sound = self.make_sound("library", "ambient")
        outside_sound = self.make_sound("outside", "ambient")
        self.player.program.collection.add(library_sound)
        listener = self.make_listener(outside_sound)
        self.vote(listener)

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertEqual(self.player.playing.layers[0].sound_id, library_sound.pk)

    def test_switching_posts_predicts_from_the_new_posts_collection(self):
        previous_sound = self.make_sound("previous-library", "ambient")
        next_sound = self.make_sound("next-library", "ambient")
        self.player.program.collection.add(previous_sound)
        listener = self.make_listener(previous_sound)
        self.vote(listener)
        self.assertEqual(self.predict(), 1)
        self.player.refresh_from_db()
        self.assertEqual(self.player.playing.layers[0].sound_id, previous_sound.pk)

        previous_post = self.player.program
        next_post = PlayerProgram.objects.create(post=Post.objects.create(
            composer=self.manager.user, title="The next player program"
        ))
        next_post.collection.add(next_sound)
        self.player.program = next_post
        self.player.save(update_fields=["program"])
        self.assertEqual(self.predict(), 1)
        self.player.refresh_from_db()
        self.assertEqual(self.player.playing.layers[0].sound_id, next_sound.pk)
        self.assertEqual(self.player.library(), [next_sound])
        self.assertEqual(list(previous_post.collection.all()), [previous_sound])

    def test_same_top_tag_uses_distinct_matching_sounds(self):
        library_one = self.make_sound("library-one", "ambient")
        library_two = self.make_sound("library-two", "ambient")
        self.player.program.collection.add(library_one, library_two)
        listener_one = self.make_listener(
            self.make_sound("collected-one", "ambient")
        )
        listener_two = self.make_listener(
            self.make_sound("collected-two", "ambient")
        )
        self.vote(listener_one)
        self.vote(listener_two)

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        sound_ids = [layer.sound_id for layer in self.player.playing.layers]
        self.assertEqual(len(sound_ids), 2)
        self.assertEqual(set(sound_ids), {library_one.pk, library_two.pk})

    def test_same_top_tag_with_one_matching_sound_adds_it_only_once(self):
        library_sound = self.make_sound("library", "ambient")
        self.player.program.collection.add(library_sound)
        listener_one = self.make_listener(
            self.make_sound("collected-one", "ambient")
        )
        listener_two = self.make_listener(
            self.make_sound("collected-two", "ambient")
        )
        self.vote(listener_one)
        self.vote(listener_two)

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertEqual(
            [layer.sound_id for layer in self.player.playing.layers],
            [library_sound.pk],
        )

    def test_empty_and_unmatched_collections_leave_prediction_unchanged(self):
        existing_sound = self.make_sound("existing", "existing")
        self.player.playing = Prediction.new()
        self.player.playing.add_layer(existing_sound.pk, gain=0.25)
        self.player.save()
        empty_listener = self.make_listener()
        unmatched = self.make_sound("unmatched", "unmatched")
        unmatched_listener = self.make_listener(unmatched)
        self.vote(empty_listener)
        self.vote(unmatched_listener)

        self.assertEqual(self.predict(), 0)

        self.player.refresh_from_db()
        self.assertEqual(len(self.player.playing.layers), 1)
        self.assertEqual(self.player.playing.layers[0].sound_id, existing_sound.pk)
        self.assertEqual(self.player.playing.layers[0].sound_gain, 0.25)

    def test_no_recent_votes_clear_existing_prediction_and_api_layers(self):
        existing_sound = self.make_sound("existing", "existing")
        self.player.playing = Prediction.new()
        self.player.playing.add_layer(existing_sound.pk, gain=0.5)
        self.player.save()
        PlayerProgram.objects.filter(pk=self.player.program_id).update(
            algorithm_active_listener_minutes=5,
            algorithm_sleep_after_minutes=5,
        )
        stale_listener = self.make_listener(existing_sound)
        self.vote(
            stale_listener,
            created_at=timezone.now() - timedelta(minutes=5, seconds=1),
        )

        with patch("core.predict.random.choice") as choice:
            self.assertEqual(self.predict(), 0)

        self.player.refresh_from_db()
        self.assertIsInstance(self.player.playing, Prediction)
        self.assertEqual(self.player.playing.layers, [])
        self.assertTrue(self.player.sleeping)
        self.assertIsNone(self.player.activated_at)
        choice.assert_not_called()

        response = self.client.get(
            "/api/player",
            headers={"X-API-Key": self.player.token},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["layers"], [])

    def test_sleeping_player_returns_before_reading_votes(self):
        Player.objects.filter(pk=self.player.pk).update(sleeping=True)

        with patch("core.predict.Vote.recent") as recent:
            self.assertEqual(self.predict(), 0)

        recent.assert_not_called()

    @override_settings(COSOUND_CORE_PREDICTOR="core.predict.random_predictor")
    def test_legacy_algorithm_uses_the_posts_sleep_window(self):
        PlayerProgram.objects.filter(pk=self.player.program_id).update(
            algorithm_active_listener_minutes=5,
            algorithm_sleep_after_minutes=10,
        )
        sound = self.make_sound("wake-up", "ambient")
        self.player.program.collection.add(sound)

        with (
            patch("core.predict.random.choice", return_value=sound.pk),
            patch.object(Player, "announce"),
        ):
            prediction = Algorithm.awaken(self.player)

        self.assertIsNotNone(prediction)
        self.player.refresh_from_db()
        activated_at = self.player.activated_at
        self.assertIsNotNone(activated_at)
        self.assertFalse(self.player.sleeping)
        self.assertEqual(
            [layer.sound_id for layer in self.player.playing.layers],
            [sound.pk],
        )

        with patch(
            "core.predict.timezone.now",
            return_value=activated_at + timedelta(minutes=10) - timedelta(seconds=1),
        ):
            self.assertEqual(self.predict(), 0)

        self.player.refresh_from_db()
        self.assertFalse(self.player.sleeping)
        self.assertEqual(
            [layer.sound_id for layer in self.player.playing.layers],
            [sound.pk],
        )

        with patch(
            "core.predict.timezone.now",
            return_value=activated_at + timedelta(minutes=10) + timedelta(seconds=1),
        ):
            self.assertEqual(self.predict(), 0)

        self.player.refresh_from_db()
        self.assertTrue(self.player.sleeping)
        self.assertIsNone(self.player.activated_at)
        self.assertEqual(self.player.playing.layers, [])

    @override_settings(COSOUND_CORE_PREDICTOR="core.predict.random_predictor")
    def test_legacy_awaken_repairs_zero_gain_and_closes_stable_exposure(self):
        sound = self.make_sound("repair", "ambient")
        self.player.program.collection.add(sound)
        silent_prediction = Prediction.new()
        silent_prediction.add_layer(sound.pk, gain=0)
        self.player.update(silent_prediction)
        decision = AlgorithmDecision.objects.create(
            player=self.player,
            policy_version="stable-preference-mixer-v2",
            outcome="selected",
        )
        exposure = PlaybackExposure.objects.create(
            player=self.player,
            opening_decision=decision,
            mix_key=f"{sound.pk}@1.000000",
            layers=[{"sound_id": sound.pk, "sound_gain": 1.0}],
        )
        Player.objects.filter(pk=self.player.pk).update(current_exposure=exposure)

        with (
            patch("core.predict.random.choice", return_value=sound.pk),
            patch.object(Player, "announce"),
        ):
            prediction = Algorithm.awaken(self.player)

        self.player.refresh_from_db()
        exposure.refresh_from_db()
        self.assertEqual(prediction.layers[0].sound_gain, 1.0)
        self.assertIsNone(self.player.current_exposure)
        self.assertEqual(exposure.status, PlaybackExposure.ENDED)
        self.assertIsNotNone(exposure.ended_at)

    @override_settings(COSOUND_CORE_PREDICTOR="core.predict.random_predictor")
    def test_legacy_awaken_renews_an_already_playing_room(self):
        sound = self.make_sound("renew", "ambient")
        self.player.program.collection.add(sound)
        playing = Prediction.new()
        playing.add_layer(sound.pk)
        previous_activation = timezone.now() - timedelta(
            minutes=self.player.program.algorithm_sleep_after_minutes
        )
        Player.objects.filter(pk=self.player.pk).update(
            playing=playing,
            sleeping=False,
            activated_at=previous_activation,
        )

        with patch("core.predict.random.choice") as choice:
            prediction = Algorithm.awaken(self.player)

        self.player.refresh_from_db()
        self.assertEqual(prediction, playing)
        self.assertGreater(self.player.activated_at, previous_activation)
        choice.assert_not_called()

    def test_algorithm_never_returns_a_deleted_prediction_after_a_failed_run(self):
        available = self.make_sound("available", "ambient")
        stale = self.make_sound("stale", "ambient")
        self.player.program.collection.add(available)
        prediction = Prediction.new()
        prediction.add_layer(stale.pk)
        Player.objects.filter(pk=self.player.pk).update(
            playing=prediction,
            sleeping=False,
        )
        stale.delete()
        predictor = Mock()
        predictor.call.return_value = 0

        with patch.object(
            Algorithm,
            "configured_predictor",
            return_value=predictor,
        ):
            result = Algorithm.awaken(self.player)

        self.assertIsNone(result)
        predictor.call.assert_called_once()

    def test_algorithm_retries_one_optimistically_discarded_awaken(self):
        available = self.make_sound("available", "ambient")
        self.player.program.collection.add(available)
        predictor = Mock()
        predictor.call.return_value = PREDICTION_RETRY

        with patch.object(
            Algorithm,
            "configured_predictor",
            return_value=predictor,
        ):
            result = Algorithm.awaken(self.player)

        self.assertIsNone(result)
        self.assertEqual(predictor.call.call_count, 2)


class SoundCreditTests(TestCase):
    """The artist named on a layer, and where pressing that name goes.

    An artist with a page of their own is reached at it directly, which is what
    keeps their profile theirs to run rather than ours to host. Everyone else
    falls back to the details modal, and the card decides between the two by
    reading this field — so what matters here is that every layer carries one,
    and that it is empty exactly when there is no page to send anybody to.
    """

    def make_sound(self, title="Rain on Tin", **fields):
        """A Sound with its embedding supplied, so save() skips the classifier."""
        return Sound.objects.create(
            file=f"sounds/{title.lower().replace(' ', '-')}.wav",
            title=title,
            embeddings=[0, 0, 0, 0, 0],
            **fields,
        )

    def test_a_layer_carries_the_artists_own_page_beside_their_name(self):
        artist = Artist.objects.create(
            name="Cameron", url="https://cameron.example/"
        )
        layer = self.make_sound(artist=artist).asLayer()

        self.assertEqual(layer["sound_artist"], "Cameron")
        self.assertEqual(layer["artist_url"], "https://cameron.example/")

    def test_an_artist_who_has_given_no_page_offers_none(self):
        """Which is what leaves the press to open our own details modal."""
        artist = Artist.objects.create(name="Sam")

        self.assertEqual(self.make_sound(artist=artist).artist_url, "")

    def test_a_legacy_credit_has_no_page_to_offer(self):
        """A name in a text column has no Artist row to keep a URL on."""
        sound = self.make_sound(artist_legacy="Field Recordist")

        self.assertEqual(sound.artist_name, "Field Recordist")
        self.assertEqual(sound.artist_url, "")

    def test_a_stored_mix_hands_the_credit_through_to_the_card(self):
        """as_layers is what the explore post and the library card mount."""
        artist = Artist.objects.create(
            name="Cameron", url="https://cameron.example/"
        )
        sound = self.make_sound(artist=artist)
        cosound = Cosound.get_or_create_from_layers([(sound.pk, 0.5)])

        [layer] = cosound.as_layers()

        self.assertEqual(layer["artist_url"], "https://cameron.example/")


class StableSelectionTests(SimpleTestCase):
    rain = SoundEvidence(1, ("rain",))
    cafe = SoundEvidence(2, ("cafe",))

    def test_candidate_counts_are_complete_and_unique(self):
        toy = tuple(SoundEvidence(index) for index in range(1, 7))
        real_size = tuple(SoundEvidence(index) for index in range(1, 18))

        toy_candidates = enumerate_candidates(toy)
        real_candidates = enumerate_candidates(real_size)

        self.assertEqual(len(toy_candidates), 41)
        self.assertEqual(len({mix.key for mix in toy_candidates}), 41)
        self.assertEqual(len(real_candidates), 833)
        self.assertEqual(
            [
                sum(len(mix.layers) == count for mix in real_candidates)
                for count in (1, 2, 3)
            ],
            [17, 136, 680],
        )
        two_to_three_layers = enumerate_candidates(
            real_size,
            min_layers=2,
            max_layers=3,
        )
        self.assertEqual(len(two_to_three_layers), 816)
        self.assertTrue(
            all(2 <= len(mix.layers) <= 3 for mix in two_to_three_layers)
        )

    def test_candidate_and_listener_order_do_not_change_the_winner(self):
        listeners = (
            ListenerEvidence("rain-listener", saved_sounds=(self.rain,)),
            ListenerEvidence("cafe-listener", saved_sounds=(self.cafe,)),
        )
        arguments = {
            "current_mix": None,
            "last_change_at": None,
            "decision_time": timezone.now(),
        }

        first = select_mix(
            sounds=(self.rain, self.cafe),
            listeners=listeners,
            **arguments,
        )
        permuted = select_mix(
            sounds=(self.cafe, self.rain),
            listeners=tuple(reversed(listeners)),
            **arguments,
        )

        self.assertEqual(first.selected_mix.key, permuted.selected_mix.key)
        self.assertEqual(first.as_dict(), permuted.as_dict())

    def test_invalid_or_duplicate_layers_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, "gain"):
            MixLayer(1, float("nan"))
        with self.assertRaisesRegex(ValueError, "same sound"):
            Mix((MixLayer(1, 1.0), MixLayer(1, 0.5)))
        with self.assertRaisesRegex(ValueError, "boolean"):
            VoteEvidence("1@1.000000", positive=1)
        with self.assertRaisesRegex(ValueError, "saved_sounds"):
            ListenerEvidence(
                "listener",
                saved_sounds=(SoundEvidence(1), SoundEvidence(1)),
            )
        with self.assertRaisesRegex(ValueError, "unique sound IDs"):
            select_mix(
                sounds=(SoundEvidence(1), SoundEvidence(1)),
                listeners=(ListenerEvidence("listener"),),
                current_mix=None,
                last_change_at=None,
                decision_time=timezone.now(),
            )
        with self.assertRaisesRegex(ValueError, "unique listener keys"):
            select_mix(
                sounds=(SoundEvidence(1),),
                listeners=(
                    ListenerEvidence("listener"),
                    ListenerEvidence("listener"),
                ),
                current_mix=None,
                last_change_at=None,
                decision_time=timezone.now(),
            )
        with self.assertRaisesRegex(ValueError, "shorter than hold_seconds"):
            SelectionConfig(hold_seconds=120, maximum_stay_seconds=60)
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            SelectionConfig(min_layers=3, max_layers=2)
        with self.assertRaisesRegex(ValueError, "baseline_sound_id"):
            SelectionConfig(baseline_sound_id=0)

    def test_saved_tag_affinity_selects_a_matching_single(self):
        listener = ListenerEvidence("listener", saved_sounds=(self.rain,))

        result = select_mix(
            sounds=(self.cafe, self.rain),
            listeners=(listener,),
            current_mix=None,
            last_change_at=None,
            decision_time=timezone.now(),
        )

        self.assertEqual(result.selected_mix.sound_ids, (self.rain.sound_id,))
        self.assertEqual(result.reason, "selected")

    def test_minimum_layers_prevents_single_layer_selection(self):
        listener = ListenerEvidence("listener", saved_sounds=(self.rain,))

        result = select_mix(
            sounds=(self.rain, self.cafe, SoundEvidence(3, ("forest",))),
            listeners=(listener,),
            current_mix=None,
            last_change_at=None,
            decision_time=timezone.now(),
            config=SelectionConfig(min_layers=2, max_layers=3),
        )

        self.assertGreaterEqual(len(result.selected_mix.layers), 2)
        self.assertLessEqual(len(result.selected_mix.layers), 3)

    def test_baseline_is_a_single_even_when_minimum_layers_is_higher(self):
        result = select_mix(
            sounds=(SoundEvidence(2), SoundEvidence(5), SoundEvidence(8)),
            listeners=(),
            current_mix=None,
            last_change_at=None,
            decision_time=timezone.now(),
            config=SelectionConfig(
                min_layers=2,
                max_layers=3,
                baseline_sound_id=5,
            ),
        )

        self.assertEqual(result.reason, "baseline_no_active_listeners")
        self.assertEqual(result.selected_mix.sound_ids, (5,))
        self.assertEqual(result.selected_mix.layers[0].gain, 1.0)

    def test_minimum_layers_degrades_to_a_smaller_library(self):
        result = select_mix(
            sounds=(self.rain,),
            listeners=(ListenerEvidence("listener"),),
            current_mix=None,
            last_change_at=None,
            decision_time=timezone.now(),
            config=SelectionConfig(min_layers=2, max_layers=3),
        )

        self.assertEqual(result.selected_mix.sound_ids, (self.rain.sound_id,))

    def test_no_listeners_without_baseline_selects_silence_even_when_awakened(self):
        sounds = (self.rain, self.cafe, SoundEvidence(3, ("forest",)))
        arguments = {
            "sounds": sounds,
            "listeners": (),
            "current_mix": None,
            "last_change_at": None,
            "decision_time": timezone.now(),
            "config": SelectionConfig(min_layers=2, max_layers=3),
        }

        idle = select_mix(**arguments)
        awakened = select_mix(**arguments, awaken=True)

        self.assertIsNone(idle.selected_mix)
        self.assertEqual(idle.reason, "silent_no_active_listeners")
        self.assertIsNone(awakened.selected_mix)
        self.assertEqual(awakened.reason, "silent_no_active_listeners")

    def test_minimum_hold_temporarily_retains_listener_mix_before_baseline(self):
        now = timezone.now()
        current = Mix((MixLayer(1, 1.0), MixLayer(2, 1.0)))
        arguments = {
            "sounds": (SoundEvidence(1), SoundEvidence(2), SoundEvidence(3)),
            "listeners": (),
            "current_mix": current,
            "decision_time": now,
            "config": SelectionConfig(
                min_layers=2,
                max_layers=3,
                hold_seconds=120,
                baseline_sound_id=3,
            ),
        }

        held = select_mix(
            **arguments,
            last_change_at=now - timedelta(seconds=119),
        )
        released = select_mix(
            **arguments,
            last_change_at=now - timedelta(seconds=121),
        )

        self.assertEqual(held.reason, "minimum_hold")
        self.assertEqual(held.selected_mix, current)
        self.assertEqual(released.reason, "baseline_no_active_listeners")
        self.assertEqual(released.selected_mix.sound_ids, (3,))

    def test_valid_mix_scores_only_one_edit_neighbours_at_four_layers(self):
        now = timezone.now()
        sounds = tuple(SoundEvidence(index) for index in range(1, 101))
        gain = 1 / math.sqrt(4)
        current = Mix(
            tuple(MixLayer(index, gain) for index in range(1, 5))
        )

        result = select_mix(
            sounds=sounds,
            listeners=(ListenerEvidence("listener"),),
            current_mix=current,
            last_change_at=now - timedelta(seconds=181),
            decision_time=now,
            config=SelectionConfig(
                min_layers=2,
                max_layers=4,
                hold_seconds=120,
                maximum_stay_seconds=180,
            ),
        )

        self.assertEqual(result.candidate_count, 4_087_875)
        self.assertEqual(result.reachable_count, 388)
        self.assertEqual(result.reason, "maximum_stay")

    def test_disagreement_penalty_can_select_a_balanced_mix(self):
        listeners = (
            ListenerEvidence("rain-listener", saved_sounds=(self.rain,)),
            ListenerEvidence("cafe-listener", saved_sounds=(self.cafe,)),
        )

        result = select_mix(
            sounds=(self.rain, self.cafe),
            listeners=listeners,
            current_mix=None,
            last_change_at=None,
            decision_time=timezone.now(),
        )

        self.assertEqual(result.selected_mix.sound_ids, (1, 2))
        self.assertAlmostEqual(result.selected_score.mean, 0.625)
        self.assertAlmostEqual(result.selected_score.disagreement, 0.0)

    def test_exact_mix_downvote_only_changes_that_candidate(self):
        rain_mix = Mix((MixLayer(1, 1.0),))
        listener = ListenerEvidence(
            "listener",
            saved_sounds=(self.rain,),
            votes=(VoteEvidence(rain_mix.key, positive=False),),
        )

        result = select_mix(
            sounds=(self.rain, self.cafe),
            listeners=(listener,),
            current_mix=None,
            last_change_at=None,
            decision_time=timezone.now(),
        )

        self.assertNotEqual(result.selected_mix.key, rain_mix.key)

    def test_hold_retains_the_current_mix(self):
        now = timezone.now()
        current = Mix((MixLayer(1, 1.0),))

        result = select_mix(
            sounds=(self.rain, self.cafe),
            listeners=(ListenerEvidence("listener", saved_sounds=(self.cafe,)),),
            current_mix=current,
            last_change_at=now - timedelta(seconds=119),
            decision_time=now,
        )

        self.assertEqual(result.selected_mix, current)
        self.assertEqual(result.reason, "minimum_hold")
        self.assertFalse(result.changed)

    def test_reachable_candidates_allow_at_most_one_layer_edit(self):
        sounds = tuple(SoundEvidence(index, (str(index),)) for index in range(1, 5))
        current = Mix((MixLayer(1, 1.0),))

        result = select_mix(
            sounds=sounds,
            listeners=(ListenerEvidence("listener"),),
            current_mix=current,
            last_change_at=timezone.now() - timedelta(minutes=3),
            decision_time=timezone.now(),
        )

        self.assertEqual(result.candidate_count, 14)
        self.assertEqual(result.reachable_count, 7)

    def test_exploration_probability_is_recorded_exactly(self):
        config = SelectionConfig(
            exploration_probability=0.05,
            exploration_size=2,
        )

        result = select_mix(
            sounds=(self.rain, self.cafe),
            listeners=(ListenerEvidence("listener", saved_sounds=(self.rain,)),),
            current_mix=None,
            last_change_at=None,
            decision_time=timezone.now(),
            config=config,
            rng=random.Random(0),
        )

        self.assertFalse(result.explored)
        self.assertAlmostEqual(result.selected_action_probability, 0.975)
        self.assertEqual(len(result.action_probabilities), 2)
        self.assertAlmostEqual(sum(dict(result.action_probabilities).values()), 1.0)

    def test_maximum_stay_forces_one_layer_edit(self):
        now = timezone.now()
        sounds = tuple(SoundEvidence(index) for index in range(1, 5))
        current = Mix(
            (
                MixLayer(1, 1 / (3**0.5)),
                MixLayer(2, 1 / (3**0.5)),
                MixLayer(3, 1 / (3**0.5)),
            )
        )
        listener = ListenerEvidence(
            "listener",
            votes=(VoteEvidence(current.key, positive=True),),
        )

        result = select_mix(
            sounds=sounds,
            listeners=(listener,),
            current_mix=current,
            last_change_at=now - timedelta(seconds=301),
            decision_time=now,
            config=SelectionConfig(
                hold_seconds=120,
                maximum_stay_seconds=300,
            ),
        )

        old_ids = set(current.sound_ids)
        new_ids = set(result.selected_mix.sound_ids)
        self.assertEqual(result.reason, "maximum_stay")
        self.assertTrue(result.changed)
        self.assertNotEqual(old_ids, new_ids)
        self.assertLessEqual(max(len(new_ids - old_ids), len(old_ids - new_ids)), 1)
        self.assertEqual(len(result.selected_mix.layers), len(current.layers))

    def test_no_active_listeners_keep_the_current_mix_after_hold(self):
        """Listener absence removes evidence; only the sleep window stops a room."""
        now = timezone.now()
        current = Mix((MixLayer(1, 1.0), MixLayer(2, 1.0)))

        result = select_mix(
            sounds=(SoundEvidence(1), SoundEvidence(2), SoundEvidence(3)),
            listeners=(),
            current_mix=current,
            last_change_at=now - timedelta(seconds=11),
            decision_time=now,
            config=SelectionConfig(
                hold_seconds=0,
                maximum_stay_seconds=10,
            ),
        )

        self.assertEqual(result.reason, "retained_no_active_listeners")
        self.assertEqual(result.selected_mix, current)
        self.assertFalse(result.changed)

    def test_no_active_listeners_retain_a_mix_however_long_it_has_played(self):
        now = timezone.now()
        current = Mix((MixLayer(1, 1.0),))

        result = select_mix(
            sounds=(SoundEvidence(1), SoundEvidence(2)),
            listeners=(),
            current_mix=current,
            last_change_at=now - timedelta(days=365),
            decision_time=now,
            config=SelectionConfig(
                hold_seconds=0,
                maximum_stay_seconds=None,
            ),
        )

        self.assertEqual(result.reason, "retained_no_active_listeners")
        self.assertEqual(result.selected_mix, current)

    def test_no_active_listeners_fall_silent_when_the_mix_left_the_library(self):
        """Nothing valid is on air to hold, so there is no playback to protect."""
        now = timezone.now()
        current = Mix((MixLayer(9, 1.0),))

        result = select_mix(
            sounds=(SoundEvidence(1), SoundEvidence(2)),
            listeners=(),
            current_mix=current,
            last_change_at=now - timedelta(seconds=600),
            decision_time=now,
            config=SelectionConfig(min_layers=1, max_layers=2, hold_seconds=0),
        )

        self.assertEqual(result.reason, "silent_no_active_listeners")
        self.assertIsNone(result.selected_mix)
        self.assertTrue(result.changed)

    def test_maximum_stay_retains_when_no_layer_edit_exists(self):
        now = timezone.now()
        current = Mix((MixLayer(1, 1.0),))

        result = select_mix(
            sounds=(SoundEvidence(1),),
            listeners=(ListenerEvidence("listener"),),
            current_mix=current,
            last_change_at=now - timedelta(seconds=11),
            decision_time=now,
            config=SelectionConfig(
                hold_seconds=0,
                maximum_stay_seconds=10,
            ),
        )

        self.assertEqual(result.reason, "maximum_stay_unavailable")
        self.assertFalse(result.changed)
        self.assertEqual(result.reachable_count, 0)


class StablePredictorIntegrationTests(TestCase):
    """The stable predictor as it behaves inside this project's lifecycle.

    These differ from the pilot branch's own integration tests because that
    branch had no sleeping state: there, a predictor ran for every player and
    a quiet room kept playing. Here a room is gated first and falls silent, so
    the setup has to wake a player deliberately.
    """

    def setUp(self):
        manager_user = User.objects.create_user(
            username="stable-manager",
            email="stable-manager@example.com",
        )
        self.manager = Manager.objects.create(user=manager_user, name="Manager")
        self.player = Player.objects.create(manager=self.manager, name="Player")
        PlayerProgram.objects.filter(pk=self.player.program_id).update(
            algorithm_exploration_probability=0.0
        )
        self.player.program.algorithm_exploration_probability = 0.0
        self.cosound = Cosound.objects.create(hashid="stable", hashset="stable")
        self.listener_number = 0

    def configure_algorithm(self, **parameters):
        """Set the admin-managed algorithm parameters for this player's program."""
        updates = {
            f"algorithm_{parameter}": value
            for parameter, value in parameters.items()
        }
        PlayerProgram.objects.filter(pk=self.player.program_id).update(**updates)
        for field, value in updates.items():
            setattr(self.player.program, field, value)

    def make_sound(self, title, *tags):
        sound = Sound.objects.create(
            file=f"sounds/{title}.mp3",
            title=title,
            embeddings=[0.0] * 5,
        )
        sound.tags.add(*tags)
        return sound

    def make_listener(self, *sounds):
        self.listener_number += 1
        number = self.listener_number
        user = User.objects.create_user(
            username=f"stable-listener-{number}",
            email=f"stable-listener-{number}@example.com",
        )
        listener = Listener.objects.create(user=user)
        listener.collection.add(*sounds)
        return listener

    def wake_playing(self, *sounds, gain=1.0):
        """Put ``sounds`` on air, which is what makes the player awake."""
        playing = Prediction.new()
        for sound in sounds:
            playing.add_layer(sound.pk, gain)
        self.player.playing = playing
        self.player.save()
        self.player.refresh_from_db()
        return playing

    def vote(self, listener, *, pleasant=Vote.UPVOTE, created_at=None):
        vote = Vote.objects.create(
            voter=listener,
            player=self.player,
            cosound=self.cosound,
            pleasant=pleasant,
        )
        if created_at is not None:
            Vote.objects.filter(pk=vote.pk).update(created_at=created_at)
        return vote

    def predict(self):
        with patch.object(Player, "announce"):
            return run_stable_prediction(self.player.pk)

    def test_sleeping_player_is_never_predicted_for(self):
        rain = self.make_sound("rain", "rain")
        self.player.program.collection.add(rain)
        self.make_listener(rain)
        self.assertTrue(self.player.sleeping)

        self.assertEqual(self.predict(), 0)

        self.player.refresh_from_db()
        self.assertTrue(self.player.sleeping)
        self.assertEqual(list(self.player.playing.layers), [])
        self.assertFalse(AlgorithmDecision.objects.exists())

    @override_settings(
        COSOUND_CORE_PREDICTOR="core.predict.stable_preference_predictor"
    )
    def test_algorithm_awaken_selects_and_records_the_configured_mix(self):
        self.configure_algorithm(
            min_layers=2,
            max_layers=4,
            exploration_probability=0.0,
        )
        sounds = [
            self.make_sound("rain", "rain"),
            self.make_sound("cafe", "cafe"),
            self.make_sound("forest", "forest"),
            self.make_sound("waves", "waves"),
        ]
        self.player.program.collection.add(*sounds)
        listener = self.make_listener()

        with patch.object(Player, "announce") as announce:
            prediction = Algorithm.awaken(self.player, listener=listener)

        self.player.refresh_from_db()
        self.assertIsNotNone(prediction)
        self.assertFalse(self.player.sleeping)
        self.assertIsNotNone(self.player.activated_at)
        self.assertEqual(
            [layer.sound_id for layer in self.player.playing.layers],
            [sounds[0].pk, sounds[1].pk],
        )
        for layer in self.player.playing.layers:
            self.assertAlmostEqual(layer.sound_gain, 1 / math.sqrt(2))
        decision = AlgorithmDecision.objects.get()
        self.assertEqual(decision.outcome, "selected")
        self.assertEqual(decision.policy_version, "stable-preference-mixer-v2")
        self.assertEqual(decision.configuration["min_layers"], 2)
        self.assertEqual(decision.configuration["max_layers"], 4)
        self.assertEqual(decision.trace["intent"], "awaken")
        self.assertEqual(self.player.current_exposure.opening_decision, decision)
        announce.assert_called_once()

    @override_settings(
        COSOUND_CORE_PREDICTOR="core.predict.stable_preference_predictor"
    )
    def test_decision_records_the_complete_post_configuration_snapshot(self):
        baseline = self.make_sound("baseline", "ambient")
        other_sound = self.make_sound("other", "ambient")
        self.player.program.collection.add(baseline, other_sound)
        self.player.program.baseline = baseline
        self.player.program.save(update_fields=["baseline"])
        self.configure_algorithm(
            refresh_interval_seconds=13,
            min_layers=1,
            max_layers=2,
            active_listener_minutes=7,
            sleep_after_minutes=31,
            minimum_hold_seconds=11,
            maximum_stay_seconds=22,
            disagreement_penalty=0.75,
            exploration_probability=0.0,
            exploration_size=3,
        )

        with patch.object(Player, "announce"):
            self.assertIsNotNone(Algorithm.awaken(self.player))

        self.assertEqual(
            AlgorithmDecision.objects.get().configuration,
            {
                "min_layers": 1,
                "max_layers": 2,
                "disagreement_penalty": 0.75,
                "hold_seconds": 11,
                "maximum_stay_seconds": 22,
                "score_precision": 8,
                "exploration_probability": 0.0,
                "exploration_size": 3,
                "baseline_sound_id": baseline.pk,
                "active_listener_minutes": 7,
                "sleep_after_minutes": 31,
                "refresh_interval_seconds": 13,
            },
        )

    @override_settings(
        COSOUND_CORE_PREDICTOR="core.predict.stable_preference_predictor"
    )
    def test_reassigning_the_post_uses_the_new_posts_policy(self):
        self.configure_algorithm(min_layers=2, max_layers=2)
        previous_post = self.player.program
        rain = self.make_sound("rain", "rain")
        cafe = self.make_sound("cafe", "cafe")
        next_post = PlayerProgram.objects.create(
            post=Post.objects.create(
                composer=self.manager.user,
                title="A single-layer post",
            ),
            algorithm_min_layers=1,
            algorithm_max_layers=1,
            algorithm_exploration_probability=0.0,
        )
        next_post.collection.add(rain, cafe)
        self.player.program = next_post
        self.player.save(update_fields=["program"])
        listener = self.make_listener(rain)

        with patch.object(Player, "announce"):
            prediction = Algorithm.awaken(self.player, listener=listener)

        self.assertEqual(previous_post.algorithm_min_layers, 2)
        self.assertEqual([layer.sound_id for layer in prediction.layers], [rain.pk])
        self.assertEqual(AlgorithmDecision.objects.get().configuration["min_layers"], 1)

    @override_settings(
        COSOUND_CORE_PREDICTOR="core.predict.stable_preference_predictor"
    )
    def test_algorithm_awaken_retries_a_library_change_during_selection(self):
        self.configure_algorithm(
            min_layers=2,
            max_layers=4,
            exploration_probability=0.0,
        )
        first = self.make_sound("rain", "rain")
        added_during_selection = self.make_sound("cafe", "cafe")
        self.player.program.collection.add(first)
        listener = self.make_listener()
        real_select_mix = run_stable_prediction.__globals__["select_mix"]
        selection_count = 0

        def select_then_change_library(**kwargs):
            nonlocal selection_count
            selection_count += 1
            result = real_select_mix(**kwargs)
            if selection_count == 1:
                self.player.program.collection.add(added_during_selection)
            return result

        with (
            patch(
                "core.prediction.live.select_mix",
                side_effect=select_then_change_library,
            ),
            patch.object(Player, "announce"),
        ):
            prediction = Algorithm.awaken(self.player, listener=listener)

        self.assertIsNotNone(prediction)
        self.assertEqual(selection_count, 2)
        self.assertEqual(len(prediction.layers), 2)
        self.assertEqual(AlgorithmDecision.objects.count(), 1)

    @override_settings(
        COSOUND_CORE_PREDICTOR="core.predict.stable_preference_predictor"
    )
    def test_algorithm_awaken_leaves_an_empty_library_sleeping(self):
        self.configure_algorithm(min_layers=2, max_layers=4)
        with patch.object(Player, "announce") as announce:
            prediction = Algorithm.awaken(self.player)

        self.player.refresh_from_db()
        self.assertIsNone(prediction)
        self.assertTrue(self.player.sleeping)
        self.assertIsNone(self.player.activated_at)
        self.assertIsNone(self.player.current_exposure)
        self.assertEqual(AlgorithmDecision.objects.get().outcome, "no_feasible_mix")
        announce.assert_not_called()

    @override_settings(
        COSOUND_CORE_PREDICTOR="core.predict.stable_preference_predictor"
    )
    def test_algorithm_awaken_uses_recent_listener_evidence(self):
        self.configure_algorithm(min_layers=1, max_layers=1)
        cafe = self.make_sound("cafe", "cafe")
        rain = self.make_sound("rain", "rain")
        self.player.program.collection.add(cafe, rain)
        self.vote(self.make_listener(rain))

        with patch.object(Player, "announce"):
            prediction = Algorithm.awaken(self.player)

        self.assertEqual([layer.sound_id for layer in prediction.layers], [rain.pk])
        self.assertEqual(AlgorithmDecision.objects.get().outcome, "selected")

    @override_settings(
        COSOUND_CORE_PREDICTOR="core.predict.stable_preference_predictor"
    )
    def test_algorithm_awaken_records_one_failure_with_its_intent(self):
        self.configure_algorithm(min_layers=1, max_layers=1)
        rain = self.make_sound("rain", "rain")
        self.player.program.collection.add(rain)

        with (
            patch(
                "core.prediction.live.select_mix",
                side_effect=RuntimeError("boom"),
            ),
            patch("core.prediction.live.logger.exception"),
        ):
            prediction = Algorithm.awaken(self.player)

        self.assertIsNone(prediction)
        self.assertEqual(AlgorithmDecision.objects.count(), 1)
        decision = AlgorithmDecision.objects.get()
        self.assertEqual(decision.outcome, "error")
        self.assertEqual(decision.trace["intent"], "awaken")

    def test_inactive_room_falls_silent_only_when_its_sleep_window_expires(self):
        """The configured sleep window, not listener absence, ends a quiet room."""
        self.configure_algorithm(sleep_after_minutes=180)
        rain = self.make_sound("rain", "rain")
        self.player.program.collection.add(rain)
        listener = self.make_listener(rain)
        with patch.object(Player, "announce"):
            self.assertIsNotNone(Algorithm.awaken(self.player, listener=listener))
        exposure = self.player.current_exposure
        now = timezone.now()
        Player.objects.filter(pk=self.player.pk).update(
            activated_at=now - timedelta(minutes=179)
        )
        # Age the exposure past the minimum hold, so the room is awake because
        # of the sleep window rather than because the mix is too young to
        # reconsider.
        PlaybackExposure.objects.filter(pk=exposure.pk).update(
            commanded_at=now - timedelta(minutes=179)
        )

        with patch("core.prediction.live.timezone.now", return_value=now):
            self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertFalse(self.player.sleeping)
        self.assertEqual(
            AlgorithmDecision.objects.latest("decided_at").outcome,
            "retained_no_active_listeners",
        )
        self.assertEqual(
            [layer.sound_id for layer in self.player.playing.layers],
            [rain.pk],
        )
        Player.objects.filter(pk=self.player.pk).update(
            activated_at=now - timedelta(minutes=181)
        )

        with patch("core.prediction.live.timezone.now", return_value=now):
            self.assertEqual(self.predict(), 0)

        self.player.refresh_from_db()
        exposure.refresh_from_db()
        self.assertTrue(self.player.sleeping)
        self.assertEqual(list(self.player.playing.layers), [])
        self.assertIsNone(self.player.current_exposure)
        self.assertEqual(exposure.status, PlaybackExposure.ENDED)
        self.assertIsNotNone(exposure.ended_at)

    def test_a_listener_too_stale_to_score_still_holds_the_room_open(self):
        """A vote inside the sleep window keeps the room awake without shaping it."""
        self.configure_algorithm(
            active_listener_minutes=5,
            sleep_after_minutes=180,
        )
        rain = self.make_sound("rain", "rain")
        self.player.program.collection.add(rain)
        self.wake_playing(rain)
        listener = self.make_listener(rain)
        now = timezone.now()
        self.vote(listener, created_at=now - timedelta(minutes=60))
        Player.objects.filter(pk=self.player.pk).update(
            activated_at=now - timedelta(minutes=181)
        )

        with patch("core.prediction.live.timezone.now", return_value=now):
            self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertFalse(self.player.sleeping)
        self.assertEqual(
            [layer.sound_id for layer in self.player.playing.layers],
            [rain.pk],
        )
        decision = AlgorithmDecision.objects.get()
        self.assertEqual(decision.active_listener_ids, [])
        self.assertEqual(decision.outcome, "retained_no_active_listeners")

    def test_a_room_sleeps_once_every_vote_ages_past_the_sleep_window(self):
        self.configure_algorithm(
            active_listener_minutes=5,
            sleep_after_minutes=180,
        )
        rain = self.make_sound("rain", "rain")
        self.player.program.collection.add(rain)
        self.wake_playing(rain)
        listener = self.make_listener(rain)
        now = timezone.now()
        self.vote(listener, created_at=now - timedelta(minutes=181))
        Player.objects.filter(pk=self.player.pk).update(
            activated_at=now - timedelta(minutes=181)
        )

        with patch("core.prediction.live.timezone.now", return_value=now):
            self.assertEqual(self.predict(), 0)

        self.player.refresh_from_db()
        self.assertTrue(self.player.sleeping)
        self.assertEqual(list(self.player.playing.layers), [])

    def test_baseline_keeps_a_freshly_active_room_playing_without_listeners(self):
        rain = self.make_sound("rain", "rain")
        self.player.program.collection.add(rain)
        self.player.program.baseline = rain
        self.player.program.save(update_fields=["baseline"])
        self.wake_playing(rain)
        Player.objects.filter(pk=self.player.pk).update(activated_at=timezone.now())

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertFalse(self.player.sleeping)
        self.assertEqual(self.player.playing.layers[0].sound_id, rain.pk)
        self.assertIsNotNone(self.player.current_exposure)
        self.assertEqual(
            AlgorithmDecision.objects.get().outcome,
            "baseline_no_active_listeners",
        )

    @override_settings(
        COSOUND_CORE_PREDICTOR="core.predict.stable_preference_predictor"
    )
    def test_awakened_room_returns_to_baseline_after_hold_without_a_vote(self):
        self.configure_algorithm(
            min_layers=2,
            max_layers=3,
            minimum_hold_seconds=120,
            maximum_stay_seconds=180,
        )
        sounds = [
            self.make_sound("rain", "rain"),
            self.make_sound("cafe", "cafe"),
            self.make_sound("forest", "forest"),
        ]
        self.player.program.collection.add(*sounds)
        self.player.program.baseline = sounds[2]
        self.player.program.save(update_fields=["baseline"])
        listener = self.make_listener()
        with patch.object(Player, "announce"):
            Algorithm.awaken(self.player, listener=listener)
        original_ids = {
            layer.sound_id for layer in self.player.playing.layers
        }
        now = timezone.now()
        started_at = now - timedelta(seconds=181)
        Player.objects.filter(pk=self.player.pk).update(activated_at=started_at)
        PlaybackExposure.objects.filter(pk=self.player.current_exposure_id).update(
            commanded_at=started_at
        )

        with (
            patch("core.prediction.live.timezone.now", return_value=now),
            patch.object(Player, "announce"),
        ):
            self.assertEqual(run_stable_prediction(self.player.pk), 1)

        self.player.refresh_from_db()
        next_ids = {layer.sound_id for layer in self.player.playing.layers}
        self.assertNotEqual(next_ids, original_ids)
        self.assertEqual(next_ids, {sounds[2].pk})
        self.assertEqual(
            AlgorithmDecision.objects.latest("decided_at").outcome,
            "baseline_no_active_listeners",
        )

    def test_selects_records_a_decision_and_then_holds(self):
        rain = self.make_sound("rain", "rain")
        cafe = self.make_sound("cafe", "cafe")
        self.player.program.collection.add(rain, cafe)
        self.wake_playing(cafe)
        self.vote(self.make_listener(rain))

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        first_exposure = self.player.current_exposure
        self.assertIsNotNone(first_exposure)
        self.assertEqual(self.player.playing.layers[0].sound_id, rain.pk)
        self.assertEqual(AlgorithmDecision.objects.count(), 1)
        decision = AlgorithmDecision.objects.get()
        self.assertEqual(decision.outcome, "selected")
        self.assertEqual(decision.trace["schema_version"], "1")
        self.assertEqual(decision.trace["decision_id"], str(decision.decision_id))
        self.assertEqual(decision.policy_version, "stable-preference-mixer-v2")
        self.assertIn("active listener equally", decision.trace["explanation"])

        # Immediately again: the minimum hold must keep the same mix, and say so.
        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertEqual(self.player.current_exposure, first_exposure)
        self.assertEqual(AlgorithmDecision.objects.count(), 2)
        self.assertEqual(
            AlgorithmDecision.objects.latest("decided_at").outcome,
            "minimum_hold",
        )

    def test_failure_retains_the_previous_mix_and_records_it(self):
        rain = self.make_sound("rain", "rain")
        self.player.program.collection.add(rain)
        self.wake_playing(rain)
        self.vote(self.make_listener(rain))

        with (
            patch(
                "core.prediction.live.select_mix",
                side_effect=RuntimeError("boom"),
            ),
            patch("core.prediction.live.logger.exception") as log_exception,
        ):
            self.assertEqual(run_stable_prediction(self.player.pk), 0)

        self.player.refresh_from_db()
        log_exception.assert_called_once()
        self.assertFalse(self.player.sleeping)
        self.assertEqual(self.player.playing.layers[0].sound_id, rain.pk)
        self.assertEqual(AlgorithmDecision.objects.count(), 1)
        self.assertEqual(AlgorithmDecision.objects.get().outcome, "error")

    def test_stale_exposure_is_closed_and_replaced(self):
        current = self.make_sound("current", "ambient")
        other = self.make_sound("old", "noise")
        self.player.program.collection.add(current, other)
        self.wake_playing(current)
        self.vote(self.make_listener(current))

        old_decision = AlgorithmDecision.objects.create(
            player=self.player,
            policy_version="stable-preference-mixer-v1",
            outcome="selected",
        )
        stale = PlaybackExposure.objects.create(
            player=self.player,
            opening_decision=old_decision,
            mix_key=f"{other.pk}@1.000000",
            layers=[{"sound_id": other.pk, "sound_gain": 1.0}],
        )
        Player.objects.filter(pk=self.player.pk).update(current_exposure=stale)

        self.predict()

        stale.refresh_from_db()
        self.player.refresh_from_db()
        self.assertEqual(stale.status, PlaybackExposure.ENDED)
        self.assertIsNotNone(stale.ended_at)
        self.assertNotEqual(self.player.current_exposure, stale)

    @patch("core.player_signals.notify_players_changed")
    def test_adopting_an_exposure_for_a_playing_mix_does_not_notify(self, notify):
        """A bootstrap writes current_exposure only; nothing audible changed.

        Publishing player.changed here would make every connected player
        re-fetch and re-evaluate a mix it is already playing.
        """
        rain = self.make_sound("rain", "rain")
        self.player.program.collection.add(rain)
        self.wake_playing(rain)
        self.vote(self.make_listener(rain))
        notify.reset_mock()

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertIsNotNone(self.player.current_exposure)
        self.assertEqual(
            AlgorithmDecision.objects.get().outcome,
            "retained_best",
        )
        notify.assert_not_called()

    def test_a_mix_that_changed_while_scoring_discards_the_decision(self):
        """Selection runs off the row lock, so the world can move under it."""
        rain = self.make_sound("rain", "rain")
        cafe = self.make_sound("cafe", "cafe")
        self.player.program.collection.add(rain, cafe)
        self.wake_playing(cafe)
        self.vote(self.make_listener(rain))

        real_select_mix = run_stable_prediction.__globals__["select_mix"]

        def select_then_interfere(**kwargs):
            result = real_select_mix(**kwargs)
            # Someone else re-mixes this player before we can commit.
            interloper = Prediction.new()
            interloper.add_layer(cafe.pk, 0.5)
            Player.objects.filter(pk=self.player.pk).update(playing=interloper)
            return result

        with (
            patch("core.prediction.live.select_mix", side_effect=select_then_interfere),
            patch("core.prediction.live.logger.info") as log_info,
        ):
            self.assertEqual(run_stable_prediction(self.player.pk), 0)

        self.player.refresh_from_db()
        self.assertEqual(self.player.playing.layers[0].sound_gain, 0.5)
        self.assertFalse(AlgorithmDecision.objects.exists())
        self.assertTrue(
            any(
                "changed while it was being scored" in str(call)
                for call in log_info.call_args_list
            )
        )

    def test_parameters_changed_while_scoring_discard_the_decision(self):
        rain = self.make_sound("rain", "rain")
        cafe = self.make_sound("cafe", "cafe")
        self.player.program.collection.add(rain, cafe)
        self.configure_algorithm(min_layers=1, max_layers=1)
        self.wake_playing(cafe)
        self.vote(self.make_listener(rain))

        real_select_mix = run_stable_prediction.__globals__["select_mix"]

        def select_then_reconfigure(**kwargs):
            result = real_select_mix(**kwargs)
            PlayerProgram.objects.filter(pk=self.player.program_id).update(
                algorithm_disagreement_penalty=0.75
            )
            return result

        with (
            patch(
                "core.prediction.live.select_mix",
                side_effect=select_then_reconfigure,
            ),
            patch("core.prediction.live.logger.info") as log_info,
        ):
            self.assertEqual(run_stable_prediction(self.player.pk), 0)

        self.player.refresh_from_db()
        self.assertEqual(self.player.playing.layers[0].sound_id, cafe.pk)
        self.assertEqual(self.player.program.algorithm_disagreement_penalty, 0.75)
        self.assertFalse(AlgorithmDecision.objects.exists())
        self.assertTrue(
            any(
                "parameters changed while it was being scored" in str(call)
                for call in log_info.call_args_list
            )
        )
