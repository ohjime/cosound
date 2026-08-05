import json

from django.test import TestCase
from django.urls import reverse

from core.models import Listener, Manager, Player, Prediction, Sound, User
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
