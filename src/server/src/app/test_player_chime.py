from unittest.mock import patch

from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings

from app.api import get_manifest, get_player
from core.models import PlayerProgram, Manager, Player, Post, Sound, User


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}


@override_settings(STORAGES=TEST_STORAGES, MEDIA_URL="/media/")
class PlayerVoteChimeAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="chime-manager",
            email="chime-manager@example.com",
        )
        self.manager = Manager.objects.create(user=self.user, name="Chime manager")
        self.player = Player.objects.create(manager=self.manager, name="Main room")
        self.sound = Sound.objects.create(
            published=True,
            title="Library sound",
            file="sounds/library.wav",
            embeddings=[0.0] * 5,
        )
        self.player.program.collection.add(self.sound)
        self.factory = RequestFactory()

    def snapshot(self, player=None):
        request = self.factory.get("/api/player")
        request.auth = player or self.player
        return get_player(request)

    def test_unconfigured_player_returns_an_empty_vote_chime(self):
        self.assertEqual(
            self.snapshot()["chime"],
            {
                "url": "",
                "version": "",
                # The level still travels: it governs the built-in tone the
                # player falls back to when no file is configured.
                "volume": settings.COSOUND_CHIME_VOLUME,
            },
        )

    def test_chime_volume_follows_the_program_without_touching_the_file(self):
        self.player.program.chime = "chimes/levelled.wav"
        self.player.program.chime_volume = 0.2
        self.player.program.save(update_fields=["chime", "chime_volume"])
        version = self.player.program.chime_version

        self.assertEqual(self.snapshot()["chime"]["volume"], 0.2)

        self.player.program.chime_volume = 0.85
        self.player.program.save(update_fields=["chime_volume"])
        chime = self.snapshot()["chime"]

        self.assertEqual(chime["volume"], 0.85)
        # A level change is not a new file: the player must not re-download.
        self.assertEqual(chime["version"], version)

    def test_player_returns_its_fallback_state_poll_interval(self):
        self.player.state_refresh_interval_seconds = 17
        self.player.save(update_fields=["state_refresh_interval_seconds"])

        self.assertEqual(
            self.snapshot()["runtime"],
            {"state_refresh_interval_seconds": 17},
        )

    def test_vote_chime_follows_the_players_current_program(self):
        original = self.player.program
        original.chime = "chimes/original.wav"
        original.save(update_fields=["chime"])
        original_version = original.chime_version

        replacement = PlayerProgram.objects.create(
            post=Post.objects.create(
                title="Replacement post",
                composer=self.user,
            ),
            chime="chimes/replacement.wav",
        )
        self.player.program = replacement
        self.player.save(update_fields=["program"])

        chime = self.snapshot()["chime"]

        self.assertTrue(chime["url"].endswith("/media/chimes/replacement.wav"))
        self.assertEqual(chime["version"], replacement.chime_version)
        self.assertNotEqual(chime["version"], original_version)

    def test_version_is_stable_when_a_signed_media_url_changes(self):
        self.player.program.chime = "chimes/stable.wav"
        self.player.program.save(update_fields=["chime"])
        storage = self.player.program.chime.storage

        with patch.object(
            storage,
            "url",
            side_effect=[
                "https://media.example/stable.wav?signature=first",
                "https://media.example/stable.wav?signature=second",
            ],
        ):
            first = self.snapshot()["chime"]
            second = self.snapshot()["chime"]

        self.assertNotEqual(first["url"], second["url"])
        self.assertEqual(first["version"], second["version"])
        self.assertEqual(first["version"], self.player.program.chime_version)

    def test_manifest_remains_the_flat_sound_library_when_chime_is_configured(self):
        self.player.program.chime = "chimes/not-a-layer.wav"
        self.player.program.save(update_fields=["chime"])
        request = self.factory.get("/api/manifest")
        request.auth = self.player

        manifest = get_manifest(request)

        self.assertEqual(set(manifest), {str(self.sound.pk)})
        self.assertNotIn("chime", manifest)
        self.assertTrue(
            manifest[str(self.sound.pk)].endswith("/media/sounds/library.wav")
        )

    def test_player_endpoint_authenticates_and_isolates_chime_metadata(self):
        self.player.program.chime = "chimes/main.wav"
        self.player.program.save(update_fields=["chime"])
        other = Player.objects.create(manager=self.manager, name="Other room")
        other.program.chime = "chimes/other.wav"
        other.program.save(update_fields=["chime"])

        self.assertEqual(self.client.get("/api/player").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/player",
                headers={"X-API-Key": "not-a-player-token"},
            ).status_code,
            401,
        )

        response = self.client.get(
            "/api/player",
            headers={"X-API-Key": self.player.token},
        )

        self.assertEqual(response.status_code, 200)
        chime = response.json()["chime"]
        self.assertEqual(chime["version"], self.player.program.chime_version)
        self.assertNotEqual(chime["version"], other.program.chime_version)
        self.assertNotIn(self.player.token, chime["url"])
        self.assertNotIn(self.player.token, chime["version"])
