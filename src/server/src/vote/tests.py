import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import (
    AlgorithmDecision,
    Listener,
    Manager,
    PlaybackExposure,
    Player,
    Prediction,
    Sound,
    User,
)
from vote.models import Vote


class SubmitVoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        manager_user = User.objects.create_user(
            username="manager",
            email="manager@example.com",
        )
        listener_user = User.objects.create_user(
            username="listener",
            email="listener@example.com",
        )
        cls.listener_user = listener_user
        cls.listener = Listener.objects.create(user=listener_user)
        cls.manager = Manager.objects.create(user=manager_user, name="Manager")

        cls.collected_sound = cls.create_sound("Already collected")
        cls.playing_sound = cls.create_sound("Currently playing")
        playing = Prediction.new()
        playing.add_layer(cls.playing_sound.pk, gain=0.75)
        cls.player = Player.objects.create(
            manager=cls.manager,
            name="Player",
            playing=playing,
        )

    @staticmethod
    def create_sound(title):
        return Sound.objects.create(
            file=f"sounds/{title.lower().replace(' ', '-')}.wav",
            title=title,
            embeddings=[0.0] * 5,
        )

    def setUp(self):
        self.client.force_login(self.listener_user)
        self.listener.collection.add(self.collected_sound)

    def submit_vote(self, choice):
        return self.client.post(
            reverse("vote:submit_vote"),
            {"player": self.player.token, "choice": choice, "section": "test"},
            headers={"HX-Request": "true"},
            query_params={
                "player": self.player.token,
                "choice": choice,
                "section": "test",
            },
        )

    def assert_vote_preserves_collection(self, choice, expected_value):
        collection_before = set(self.listener.collection.values_list("pk", flat=True))

        response = self.submit_vote(choice)

        self.assertEqual(response.status_code, 200)
        vote = Vote.objects.get()
        self.assertEqual(vote.voter, self.listener)
        self.assertEqual(vote.player, self.player)
        self.assertEqual(vote.value, expected_value)
        self.assertEqual(vote.section, "test")
        self.assertIsNone(vote.exposure)
        self.assertEqual(vote.attribution_quality, Vote.UNATTRIBUTED)
        self.assertSetEqual(
            set(self.listener.collection.values_list("pk", flat=True)),
            collection_before,
        )
        trigger = json.loads(response.headers["HX-Trigger"])
        self.assertIn("vote-success", trigger)
        self.assertEqual(trigger["vote-success"]["voters"][0]["id"], vote.pk)

    def test_upvote_records_vote_without_changing_collection(self):
        self.assert_vote_preserves_collection(choice="1", expected_value=1)

    def test_downvote_records_vote_without_changing_collection(self):
        self.assert_vote_preserves_collection(choice="0", expected_value=0)

    def make_current_exposure(self):
        decision = AlgorithmDecision.objects.create(
            player=self.player,
            policy_version="test-v1",
            outcome="selected",
        )
        exposure = PlaybackExposure.objects.create(
            player=self.player,
            opening_decision=decision,
            mix_key=f"{self.playing_sound.pk}@0.750000",
            layers=[
                {"sound_id": self.playing_sound.pk, "sound_gain": 0.75}
            ],
        )
        self.player.current_exposure = exposure
        self.player.save(update_fields=["current_exposure"])
        return exposure

    def test_vote_links_to_unacknowledged_current_exposure(self):
        exposure = self.make_current_exposure()

        response = self.submit_vote("1")

        self.assertEqual(response.status_code, 200)
        vote = Vote.objects.get()
        self.assertEqual(vote.exposure, exposure)
        self.assertEqual(vote.attribution_quality, Vote.SERVER_CURRENT)

    def test_vote_during_acknowledged_transition_is_marked_uncertain(self):
        exposure = self.make_current_exposure()
        now = timezone.now()
        exposure.acknowledged_at = now
        exposure.transition_seconds = 10
        exposure.estimated_audible_at = now + timedelta(seconds=10)
        exposure.status = PlaybackExposure.PLAYER_ACKNOWLEDGED
        exposure.save()

        response = self.submit_vote("1")

        self.assertEqual(response.status_code, 200)
        vote = Vote.objects.get()
        self.assertEqual(vote.exposure, exposure)
        self.assertEqual(vote.attribution_quality, Vote.TRANSITION_UNCERTAIN)

    def test_vote_after_transition_uses_acknowledged_attribution(self):
        exposure = self.make_current_exposure()
        now = timezone.now()
        exposure.acknowledged_at = now - timedelta(seconds=20)
        exposure.transition_seconds = 10
        exposure.estimated_audible_at = now - timedelta(seconds=10)
        exposure.status = PlaybackExposure.PLAYER_ACKNOWLEDGED
        exposure.save()

        response = self.submit_vote("1")

        self.assertEqual(response.status_code, 200)
        vote = Vote.objects.get()
        self.assertEqual(vote.exposure, exposure)
        self.assertEqual(vote.attribution_quality, Vote.PLAYER_ACKNOWLEDGED)

    def test_mismatched_exposure_is_not_attributed(self):
        exposure = self.make_current_exposure()
        exposure.mix_key = "999@1.000000"
        exposure.save(update_fields=["mix_key"])

        response = self.submit_vote("1")

        self.assertEqual(response.status_code, 200)
        vote = Vote.objects.get()
        self.assertIsNone(vote.exposure)
        self.assertEqual(vote.attribution_quality, Vote.UNATTRIBUTED)
