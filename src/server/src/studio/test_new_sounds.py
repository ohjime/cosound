"""An artist's new sound, from the card to a Sound row, and who may hear it.

A new sound is created by the save dialog (studio:create_sound) and saved into
a mix straight after. It starts unpublished: its own artist builds with it, and
nobody else meets it — not in the picker, not in their saved mixes, not on a
player — until staff publish it from the admin.
"""

import io
import json
from tempfile import TemporaryDirectory

import numpy as np
import soundfile as sf
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from app.utils import serialize_mix
from core.admin import SoundAdmin
from core.models import Artist, Cosound, Listener, Manager, Player, Sound
from library.models import SoundMix


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def wav_upload(name="rain.wav"):
    buffer = io.BytesIO()
    samples = np.sin(np.linspace(0, 440 * 2 * np.pi, 8000)).astype("float32") * 0.2
    sf.write(buffer, samples, 8000, format="WAV")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="audio/wav")


def png_upload(name="art.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "teal").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def make_sound(title, **fields):
    return Sound.objects.create(
        file=f"sounds/{title.lower().replace(' ', '-')}.wav",
        title=title,
        embeddings=[0, 0, 0, 0, 0],
        **fields,
    )


class MediaTestCase(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(
            MEDIA_ROOT=self.media.name, MEDIA_URL="/media/", STORAGES=TEST_STORAGES
        )
        override.enable()
        self.addCleanup(override.disable)


class CreateSoundTests(MediaTestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.artist_user = User.objects.create_user(
            username="maker", email="maker@example.com", password="pw"
        )
        cls.artist = Artist.objects.create(user=cls.artist_user, name="Maker")
        cls.listener = User.objects.create_user(
            username="listener", email="listener@example.com", password="pw"
        )
        make_sound("Tagged", published=True).tags.add("Rain")

    def post(self, **overrides):
        data = {
            "file": wav_upload(),
            "art": png_upload(),
            "title": "Tin roof",
            "flavor": "Rain on the shed.",
            "tags": "Rain\nNot a tag",
        }
        data.update(overrides)
        data = {key: value for key, value in data.items() if value is not None}
        return self.client.post(reverse("studio:create_sound"), data)

    def test_signed_out_and_non_artists_are_refused(self):
        self.assertEqual(self.post().status_code, 401)
        self.client.force_login(self.listener)
        self.assertEqual(self.post().status_code, 403)
        self.assertFalse(Sound.objects.filter(title="Tin roof").exists())

    def test_creates_an_unpublished_sound_credited_to_the_artist(self):
        self.client.force_login(self.artist_user)
        response = self.post()

        self.assertEqual(response.status_code, 201)
        sound = Sound.objects.get(title="Tin roof")
        self.assertFalse(sound.published)
        self.assertEqual(sound.artist, self.artist)
        self.assertEqual(sound.flavor, "Rain on the shed.")
        self.assertTrue(sound.file.name.startswith("sounds/"))
        self.assertTrue(sound.art.name.startswith("sound_arts/"))
        # Only tags cosound already has; the card offers nothing else.
        self.assertEqual(list(sound.tags.names()), ["Rain"])

        layer = response.json()["layer"]
        self.assertEqual(layer["sound_id"], sound.pk)
        self.assertEqual(layer["sound_artist"], "Maker")
        self.assertIs(layer["published"], False)

    def test_refuses_a_file_that_is_not_audio(self):
        self.client.force_login(self.artist_user)
        response = self.post(
            file=SimpleUploadedFile("rain.wav", b"not audio", content_type="audio/wav")
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("audio file", response.json()["error"])
        self.assertFalse(Sound.objects.filter(title="Tin roof").exists())

    def test_requires_artwork_and_a_title(self):
        self.client.force_login(self.artist_user)
        self.assertEqual(self.post(art=None).status_code, 400)
        self.assertEqual(self.post(title="").status_code, 400)
        self.assertFalse(Sound.objects.filter(title="Tin roof").exists())

    def test_a_created_sound_saves_into_a_mix_that_lists_it(self):
        self.client.force_login(self.artist_user)
        sound_id = self.post().json()["layer"]["sound_id"]

        response = self.client.post(
            reverse("library:save_confirm"),
            {"layers": json.dumps([{"sound_id": sound_id, "sound_gain": 0.5}]), "title": "Shed"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("mix-saved", json.loads(response["HX-Trigger"]))
        saved = self.client.get(reverse("library:saved_list"), HTTP_HX_REQUEST="true")
        self.assertContains(saved, "Shed")
        self.assertContains(saved, "Tin roof")


class SaveWithNewSoundsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="saver", email="saver@example.com", password="pw"
        )
        cls.sound = make_sound("Wind", published=True)

    def setUp(self):
        self.client.force_login(self.user)

    def test_the_dialog_counts_new_sounds_and_warns_they_are_final(self):
        layers = [
            {"sound_id": self.sound.pk, "sound_gain": 1},
            {"sound_id": "draft-1", "sound_gain": 0.5, "is_new": True},
        ]
        response = self.client.post(
            reverse("library:save"), {"layers": json.dumps(layers)}, HTTP_HX_REQUEST="true"
        )

        self.assertContains(response, "Saving uploads your 1 new sound.")
        self.assertContains(response, "can't be changed")
        self.assertContains(response, 'hx-trigger="sounds-created"')
        self.assertContains(response, reverse("studio:create_sound"))

    def test_a_mix_of_only_new_sounds_still_opens_the_dialog(self):
        layers = [{"sound_id": "draft-1", "sound_gain": 0.5, "is_new": True}]
        response = self.client.post(
            reverse("library:save"), {"layers": json.dumps(layers)}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)

    def test_confirm_refuses_a_new_sound_that_was_not_created_first(self):
        layers = [
            {"sound_id": self.sound.pk, "sound_gain": 1},
            {"sound_id": "draft-1", "sound_gain": 0.5, "is_new": True},
        ]
        response = self.client.post(
            reverse("library:save_confirm"),
            {"layers": json.dumps(layers), "title": "Half"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SoundMix.objects.filter(creator=self.user).exists())


class UnpublishedVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(
            username="owner", email="owner@example.com", password="pw"
        )
        Artist.objects.create(user=cls.owner, name="Owner")
        cls.stranger = User.objects.create_user(
            username="stranger", email="stranger@example.com", password="pw"
        )
        cls.pending = make_sound("Pending hum", artist=cls.owner.artist_set.get())
        cls.pending.tags.add("Hum")
        cls.public = make_sound("Public hum", published=True)
        cls.public.tags.add("Hum")

    def search(self, user):
        self.client.force_login(user)
        return self.client.get(
            reverse("library:search"), {"q": "hum"}, HTTP_HX_REQUEST="true"
        )

    def test_only_the_owner_finds_an_unpublished_sound_and_sees_it_flagged(self):
        owner = self.search(self.owner)
        self.assertContains(owner, "Pending hum")
        self.assertContains(owner, "Unpublished")

        stranger = self.search(self.stranger)
        self.assertNotContains(stranger, "Pending hum")
        self.assertContains(stranger, "Public hum")
        self.assertNotContains(stranger, "Unpublished")

    def test_a_stranger_cannot_keep_or_save_it(self):
        self.client.force_login(self.stranger)
        keep = self.client.post(
            reverse("library:keep_sound"), {"sound_id": self.pending.pk}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(keep.status_code, 404)

        save = self.client.post(
            reverse("library:save_confirm"),
            {"layers": json.dumps([{"sound_id": self.pending.pk, "sound_gain": 1}]), "title": "Nope"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(save.status_code, 400)

    def test_the_owners_favourites_flag_it(self):
        listener, _ = Listener.objects.get_or_create(user=self.owner)
        listener.collection.add(self.pending)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("library:liked_list"), HTTP_HX_REQUEST="true")
        self.assertContains(response, "Pending hum")
        self.assertContains(response, "Unpublished")

    def test_a_pulled_sound_drops_out_of_other_listeners_saved_mixes(self):
        cosound = Cosound.get_or_create_from_layers([(self.pending.pk, 1), (self.public.pk, 1)])
        theirs = SoundMix.objects.create(creator=self.stranger, cosound=cosound, title="T")
        mine = SoundMix.objects.create(creator=self.owner, cosound=cosound, title="M")

        self.assertEqual(
            [layer["sound_title"] for layer in serialize_mix(theirs)["layers"]], ["Public hum"]
        )
        self.assertEqual(len(serialize_mix(mine)["layers"]), 2)

    def test_players_never_get_an_unpublished_sound(self):
        manager = Manager.objects.create(user=self.stranger, name="Venue")
        player = Player.objects.create(manager=manager, name="Room")
        player.program.collection.add(self.pending, self.public)

        self.assertEqual(player.library(), [self.public])


class SoundAdminPublishTests(TestCase):
    def test_publish_and_unpublish_actions_flip_the_flag(self):
        sound = make_sound("Review me")
        admin = SoundAdmin(Sound, site)
        request = RequestFactory().post("/")
        request._messages = type("M", (), {"add": lambda *args, **kwargs: None})()

        admin.publish_sounds(request, Sound.objects.filter(pk=sound.pk))
        sound.refresh_from_db()
        self.assertTrue(sound.published)

        admin.unpublish_sounds(request, Sound.objects.filter(pk=sound.pk))
        sound.refresh_from_db()
        self.assertFalse(sound.published)
