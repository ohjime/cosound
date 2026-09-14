import random
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from taggit.models import Tag

from core.management.commands.refresh import Command, REFRESH_INTERVAL_SECONDS, _get_predictor
from core.models import (
    AlgorithmDecision,
    Cosound,
    Listener,
    Manager,
    PlaybackExposure,
    Player,
    Prediction,
    Sound,
    User,
)
from core.predict import (
    _predict_for_player,
    _stable_predict_for_player,
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
from vote.models import Vote


class RefreshSchedulerTests(SimpleTestCase):
    @override_settings(
        COSOUND_CORE_PREDICTOR="core.predict.stable_preference_predictor"
    )
    def test_can_select_the_stable_predictor_by_setting(self):
        self.assertIs(_get_predictor(), stable_preference_predictor)

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
    @patch("core.management.commands.refresh.Player.objects.all", return_value=[])
    @patch("core.management.commands.refresh._get_predictor")
    def test_waits_thirty_seconds_between_player_refreshes(
        self,
        _get_predictor,
        _players,
        sleep,
    ):
        with self.assertRaises(SystemExit) as stopped:
            Command().handle()

        self.assertEqual(stopped.exception.code, 0)
        self.assertEqual(REFRESH_INTERVAL_SECONDS, 30)
        sleep.assert_called_once_with(30)


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
            value=Vote.UPVOTE,
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
        self.assertEqual(self.vote.value, Vote.UPVOTE)
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


class PredictorTests(TestCase):
    def setUp(self):
        manager_user = User.objects.create_user(
            username="manager",
            email="manager@example.com",
            password="password",
        )
        self.manager = Manager.objects.create(user=manager_user, name="Manager")
        self.player = Player.objects.create(manager=self.manager, name="Player")

    def make_sound(self, title):
        return Sound.objects.create(
            file=f"sounds/{title}.mp3",
            title=title,
            embeddings=[0.0] * 5,
        )

    def predict(self):
        with patch.object(Player, "announce"):
            return _predict_for_player(self.player.pk)

    def test_builds_three_random_layers_from_the_library(self):
        sounds = [self.make_sound(f"sound-{i}") for i in range(5)]
        self.player.sounds.add(*sounds)

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        layers = self.player.playing.layers
        self.assertEqual(len(layers), 3)
        sound_ids = [layer.sound_id for layer in layers]
        self.assertEqual(len(set(sound_ids)), 3)
        self.assertTrue(set(sound_ids) <= {sound.pk for sound in sounds})
        for layer in layers:
            self.assertGreaterEqual(layer.sound_gain, 0.0)
            self.assertLessEqual(layer.sound_gain, 1.0)

    def test_uses_the_whole_library_when_there_are_fewer_than_three_sounds(self):
        first = self.make_sound("first")
        second = self.make_sound("second")
        self.player.sounds.add(first, second)

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertEqual(len(self.player.playing.layers), 2)
        self.assertEqual(
            {layer.sound_id for layer in self.player.playing.layers},
            {first.pk, second.pk},
        )

    def test_does_not_use_sounds_outside_the_library(self):
        library_sound = self.make_sound("library")
        self.make_sound("outside")
        self.player.sounds.add(library_sound)

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        self.assertEqual(
            [layer.sound_id for layer in self.player.playing.layers],
            [library_sound.pk],
        )

    def test_empty_library_clears_existing_prediction(self):
        existing_sound = self.make_sound("existing")
        self.player.playing = Prediction.new()
        self.player.playing.add_layer(existing_sound.pk, gain=0.5)
        self.player.save()

        self.assertEqual(self.predict(), 0)

        self.player.refresh_from_db()
        self.assertEqual(self.player.playing.layers, [])

    def test_random_rollback_closes_stable_exposure_attribution(self):
        sound = self.make_sound("sound")
        self.player.sounds.add(sound)
        decision = AlgorithmDecision.objects.create(
            player=self.player,
            policy_version="stable-preference-mixer-v1",
            outcome="selected",
        )
        exposure = PlaybackExposure.objects.create(
            player=self.player,
            opening_decision=decision,
            mix_key=f"{sound.pk}@1.000000",
            layers=[{"sound_id": sound.pk, "sound_gain": 1.0}],
        )
        self.player.current_exposure = exposure
        self.player.save(update_fields=["current_exposure"])

        self.assertEqual(self.predict(), 1)

        self.player.refresh_from_db()
        exposure.refresh_from_db()
        self.assertIsNone(self.player.current_exposure)
        self.assertEqual(exposure.status, PlaybackExposure.ENDED)
        self.assertIsNotNone(exposure.ended_at)


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

    def test_house_fallback_respects_minimum_layers(self):
        result = select_mix(
            sounds=(SoundEvidence(2), SoundEvidence(5), SoundEvidence(8)),
            listeners=(),
            current_mix=None,
            last_change_at=None,
            decision_time=timezone.now(),
            config=SelectionConfig(
                min_layers=2,
                max_layers=3,
                house_sound_id=5,
            ),
        )

        self.assertEqual(result.reason, "house_mix_no_active_listeners")
        self.assertEqual(len(result.selected_mix.layers), 2)
        self.assertIn(5, result.selected_mix.sound_ids)

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

    def test_maximum_stay_rotates_without_active_listeners(self):
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
                house_sound_id=None,
            ),
        )

        self.assertEqual(result.reason, "maximum_stay")
        self.assertNotEqual(result.selected_mix.sound_ids, current.sound_ids)
        self.assertEqual(len(result.selected_mix.layers), 2)

    def test_maximum_stay_can_be_indefinite(self):
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

    def test_maximum_stay_retains_when_no_layer_edit_exists(self):
        now = timezone.now()
        current = Mix((MixLayer(1, 1.0),))

        result = select_mix(
            sounds=(SoundEvidence(1),),
            listeners=(),
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
    def setUp(self):
        manager_user = User.objects.create_user(
            username="stable-manager",
            email="stable-manager@example.com",
        )
        listener_user = User.objects.create_user(
            username="stable-listener",
            email="stable-listener@example.com",
        )
        self.manager = Manager.objects.create(user=manager_user, name="Manager")
        self.listener = Listener.objects.create(user=listener_user)
        self.player = Player.objects.create(manager=self.manager, name="Player")

    def make_sound(self, title, *tags):
        sound = Sound.objects.create(
            file=f"sounds/{title}.mp3",
            title=title,
            embeddings=[0.0] * 5,
        )
        sound.tags.add(*tags)
        return sound

    def make_active(self, sound, *, value=Vote.UPVOTE):
        cosound = Cosound.get_or_create_from_layers([(sound.pk, 1.0)])
        return Vote.objects.create(
            voter=self.listener,
            player=self.player,
            cosound=cosound,
            value=value,
        )

    def test_stable_predictor_selects_records_and_holds(self):
        rain = self.make_sound("rain", "rain")
        cafe = self.make_sound("cafe", "cafe")
        self.player.sounds.add(rain, cafe)
        self.listener.collection.add(rain)
        self.make_active(cafe)

        with patch.object(Player, "announce"):
            self.assertEqual(_stable_predict_for_player(self.player.pk), 1)

        self.player.refresh_from_db()
        first_exposure = self.player.current_exposure
        self.assertIsNotNone(first_exposure)
        self.assertEqual(self.player.playing.layers[0].sound_id, rain.pk)
        self.assertEqual(AlgorithmDecision.objects.count(), 1)
        decision = AlgorithmDecision.objects.get()
        self.assertEqual(decision.trace["schema_version"], "1")
        self.assertEqual(decision.trace["decision_id"], str(decision.decision_id))
        self.assertIn("active listener equally", decision.trace["explanation"])

        with patch.object(Player, "announce"):
            self.assertEqual(_stable_predict_for_player(self.player.pk), 1)

        self.player.refresh_from_db()
        self.assertEqual(self.player.current_exposure, first_exposure)
        self.assertEqual(AlgorithmDecision.objects.count(), 2)
        self.assertEqual(
            AlgorithmDecision.objects.latest("decided_at").outcome,
            "minimum_hold",
        )

    def test_predictor_failure_retains_the_previous_mix(self):
        sound = self.make_sound("existing", "ambient")
        self.player.sounds.add(sound)
        playing = Prediction.new()
        playing.add_layer(sound.pk, 1.0)
        self.player.playing = playing
        self.player.save()

        with (
            patch(
                "core.prediction.live.select_mix",
                side_effect=RuntimeError("boom"),
            ),
            patch("core.prediction.live.logger.exception") as log_exception,
        ):
            self.assertEqual(_stable_predict_for_player(self.player.pk), 0)

        self.player.refresh_from_db()
        log_exception.assert_called_once()
        self.assertEqual(self.player.playing.layers[0].sound_id, sound.pk)
        self.assertEqual(AlgorithmDecision.objects.count(), 1)
        self.assertEqual(AlgorithmDecision.objects.get().outcome, "error")

    def test_no_active_listener_retains_current_and_bootstraps_exposure(self):
        sound = self.make_sound("existing", "ambient")
        self.player.sounds.add(sound)
        playing = Prediction.new()
        playing.add_layer(sound.pk, 1.0)
        self.player.playing = playing
        self.player.save()

        self.assertEqual(_stable_predict_for_player(self.player.pk), 1)

        self.player.refresh_from_db()
        self.assertIsNotNone(self.player.current_exposure)
        self.assertEqual(
            AlgorithmDecision.objects.get().outcome,
            "retained_no_active_listeners",
        )

    def test_stale_exposure_is_closed_and_replaced(self):
        sound = self.make_sound("current", "ambient")
        other = self.make_sound("old", "noise")
        self.player.sounds.add(sound, other)
        playing = Prediction.new()
        playing.add_layer(sound.pk, 1.0)
        self.player.playing = playing
        old_decision = AlgorithmDecision.objects.create(
            player=self.player,
            policy_version="stable-preference-mixer-v1",
            outcome="selected",
        )
        stale_exposure = PlaybackExposure.objects.create(
            player=self.player,
            opening_decision=old_decision,
            mix_key=f"{other.pk}@1.000000",
            layers=[{"sound_id": other.pk, "sound_gain": 1.0}],
        )
        self.player.current_exposure = stale_exposure
        self.player.save(update_fields=["playing", "current_exposure"])

        self.assertEqual(_stable_predict_for_player(self.player.pk), 1)

        self.player.refresh_from_db()
        stale_exposure.refresh_from_db()
        self.assertEqual(stale_exposure.status, PlaybackExposure.ENDED)
        self.assertIsNotNone(stale_exposure.ended_at)
        self.assertNotEqual(self.player.current_exposure, stale_exposure)
        self.assertEqual(
            self.player.current_exposure.mix_key,
            f"{sound.pk}@1.000000",
        )

    @override_settings(
        COSOUND_MINIMUM_HOLD_SECONDS=0,
        COSOUND_MAX_STAY_SECONDS=1,
    )
    def test_maximum_stay_closes_exposure_and_changes_one_sound(self):
        first = self.make_sound("first", "ambient")
        second = self.make_sound("second", "nature")
        self.player.sounds.add(first, second)
        playing = Prediction.new()
        playing.add_layer(first.pk, 1.0)
        self.player.playing = playing
        opening_decision = AlgorithmDecision.objects.create(
            player=self.player,
            policy_version="stable-preference-mixer-v1",
            outcome="selected",
        )
        old_exposure = PlaybackExposure.objects.create(
            player=self.player,
            opening_decision=opening_decision,
            mix_key=f"{first.pk}@1.000000",
            layers=[{"sound_id": first.pk, "sound_gain": 1.0}],
            commanded_at=timezone.now() - timedelta(seconds=2),
        )
        self.player.current_exposure = old_exposure
        self.player.save(update_fields=["playing", "current_exposure"])

        with patch.object(Player, "announce"):
            self.assertEqual(_stable_predict_for_player(self.player.pk), 1)

        self.player.refresh_from_db()
        old_exposure.refresh_from_db()
        self.assertEqual(old_exposure.status, PlaybackExposure.ENDED)
        self.assertEqual(self.player.playing.layers[0].sound_id, second.pk)
        self.assertEqual(
            AlgorithmDecision.objects.latest("decided_at").outcome,
            "maximum_stay",
        )
