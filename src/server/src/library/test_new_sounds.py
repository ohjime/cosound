"""An artist's new sound, from the card to a Sound row, and who may hear it.

A new sound is created by the save dialog (library:create_sound) and saved
into a mix straight after. On the way in it is baked: the loop check the artist
heard — the crop, the crossfade folded into the seam, the loudness — goes into
the file itself (core.audio). It starts unpublished: its own artist builds with
it, and nobody else meets it — not in the picker, not in their saved mixes, not
on a player — until staff publish it from the admin.
"""

import io
import json
import math
from tempfile import TemporaryDirectory

import numpy as np
import soundfile as sf
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import NoReverseMatch, reverse
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


RATE = 8000


def tone_upload(seconds=3.0, frequency=441.3, amplitude=0.1, name="tone.wav", format="WAV"):
    """A steady stereo tone whose period does not fit a whole number of times
    into any of the crops these tests take — so looped raw, its end would jump
    to its start, and only a real fold makes the join disappear."""
    t = np.arange(int(seconds * RATE)) / RATE
    tone = (amplitude * np.sin(2 * np.pi * frequency * t)).astype("float32")
    buffer = io.BytesIO()
    sf.write(buffer, np.stack([tone, tone], axis=1), RATE, format=format)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="audio/wav")


def stored_audio(sound):
    with sound.file.open("rb") as stored:
        data, rate = sf.read(io.BytesIO(stored.read()), dtype="float32", always_2d=True)
    return data, rate


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
        return self.client.post(reverse("library:create_sound"), data)

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


class BakeTests(MediaTestCase):
    """What the loop check becomes in the stored file."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="baker", email="baker@example.com", password="pw"
        )
        Artist.objects.create(user=cls.user, name="Baker")

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def create(self, file, **loop_check):
        data = {"file": file, "art": png_upload(), "title": "Loop", **loop_check}
        response = self.client.post(reverse("library:create_sound"), data)
        self.assertEqual(response.status_code, 201, response.content)
        return Sound.objects.get(pk=response.json()["layer"]["sound_id"])

    def test_the_crop_and_crossfade_are_folded_into_a_seamless_flac(self):
        sound = self.create(
            tone_upload(), trim_start=0.2, trim_end=2.8, loop_crossfade=0.4
        )
        data, rate = stored_audio(sound)

        self.assertTrue(sound.file.name.endswith(".flac"))
        # The crop kept 2.6s and the fold took the last 0.4s of it into the head.
        self.assertEqual(data.shape[0], round((2.6 - 0.4) * RATE))
        self.assertAlmostEqual(sound.duration, 2.2)
        self.assertAlmostEqual(sound.trim_start, 0.2)
        self.assertAlmostEqual(sound.trim_end, 2.8)
        self.assertAlmostEqual(sound.loop_crossfade, 0.4)
        self.assertTrue(sound.seamless)
        # Played back to back, the join is no bigger a step than any other
        # sample-to-sample step in the file.
        loop = np.concatenate([data, data])[:, 0]
        steps = np.abs(np.diff(loop))
        self.assertLessEqual(steps[data.shape[0] - 1], steps.max() + 1e-6)

    def test_an_unfolded_crop_of_the_same_tone_would_click(self):
        # The control for the test above: the tone really does jump at a raw
        # join, so a smooth one means the fold did something.
        t = np.arange(int(3.0 * RATE)) / RATE
        tone = 0.1 * np.sin(2 * np.pi * 441.3 * t)
        region = tone[round(0.2 * RATE):round(2.8 * RATE)]
        inner = np.abs(np.diff(region)).max()
        self.assertGreater(abs(region[0] - region[-1]), inner * 1.5)

    def test_the_sound_is_levelled_to_the_target_it_was_checked_at(self):
        sound = self.create(tone_upload(amplitude=0.1), loudness=-23.0, loudness_target=-20.0)
        data, _ = stored_audio(sound)

        self.assertAlmostEqual(sound.loudness_gain_db, 3.0, places=3)
        self.assertAlmostEqual(sound.loudness_lufs, -20.0, places=3)
        self.assertAlmostEqual(float(np.abs(data).max()), 0.1 * 10 ** (3 / 20), places=3)

    def test_levelling_never_lifts_a_peak_past_the_ceiling(self):
        # +6 dB asked for, on a tone already peaking at -0.9 dBFS.
        sound = self.create(tone_upload(amplitude=0.9), loudness=-20.0, loudness_target=-14.0)
        data, _ = stored_audio(sound)

        self.assertLessEqual(20 * math.log10(float(np.abs(data).max())), -1.0 + 0.01)
        self.assertLess(sound.loudness_gain_db, 0.0)

    def test_an_untouched_flac_is_stored_as_it_came(self):
        upload = tone_upload(name="loop.flac", format="FLAC")
        original = upload.read()
        upload.seek(0)
        sound = self.create(upload)

        with sound.file.open("rb") as stored:
            self.assertEqual(stored.read(), original)
        self.assertEqual(sound.loudness_gain_db, 0.0)
        self.assertIsNone(sound.loudness_lufs, "nothing was measured, so nothing is claimed")

    def test_a_loop_check_the_file_cannot_hold_is_refused(self):
        refused = {
            "a crop under a quarter second": {"trim_start": 1.0, "trim_end": 1.1},
            "a crossfade over half the crop": {"trim_start": 0, "trim_end": 2, "loop_crossfade": 1.5},
            "a target past the nudge": {"loudness_target": -40},
        }
        for case, loop_check in refused.items():
            with self.subTest(case):
                data = {"file": tone_upload(), "art": png_upload(), "title": "No", **loop_check}
                response = self.client.post(reverse("library:create_sound"), data)
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Sound.objects.filter(title="No").exists())

    def test_the_finished_layer_says_it_is_a_seamless_loop(self):
        response = self.client.post(
            reverse("library:create_sound"),
            {"file": tone_upload(), "art": png_upload(), "title": "Loop", "loudness": -23},
        )
        layer = response.json()["layer"]

        self.assertIs(layer["seamless"], True)
        self.assertAlmostEqual(layer["loudness_lufs"], -20.0, places=3)


class TagSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="tag-artist", email="tag-artist@example.com", password="pw"
        )
        Artist.objects.create(user=cls.user, name="Tag Artist")
        sound = make_sound("Tagged", published=True)
        sound.tags.add("Rain", "Rainforest", "Night")

    def search(self, **params):
        return self.client.get(
            reverse("library:tag_search"), params, HTTP_HX_REQUEST="true"
        )

    def test_only_artists_may_search(self):
        self.assertEqual(self.search(q="rain").status_code, 403)

    def test_offers_existing_tags_and_no_request_link_on_an_exact_match(self):
        self.client.force_login(self.user)
        response = self.search(q="rain")
        self.assertContains(response, 'data-tag="Rain"')
        self.assertContains(response, 'data-tag="Rainforest"')
        self.assertNotContains(response, 'data-tag="Night"')
        self.assertNotContains(response, "Ask cosound to add")

    def test_leaves_out_tags_the_layer_already_has(self):
        self.client.force_login(self.user)
        response = self.search(q="rain", chosen="Rain")
        self.assertNotContains(response, 'data-tag="Rain"')
        self.assertContains(response, 'data-tag="Rainforest"')

    def test_an_unknown_tag_offers_to_ask_cosound(self):
        self.client.force_login(self.user)
        response = self.search(q="thunder")
        self.assertNotContains(response, "data-tag=")
        self.assertContains(response, "No tag matches “thunder”")
        self.assertContains(response, "Ask cosound to add it")

    def test_a_half_typed_tag_does_not_offer_the_request_link(self):
        self.client.force_login(self.user)
        response = self.search(q="nig")
        self.assertContains(response, 'data-tag="Night"')
        self.assertNotContains(response, "Ask cosound to add")

    def test_an_empty_query_answers_nothing(self):
        self.client.force_login(self.user)
        response = self.search(q="  ")
        self.assertEqual(response.content, b"")


class StudioGoneTests(TestCase):
    """The studio's builder, routes and host are gone; the LIBRARY card is it."""

    def test_no_studio_route_resolves(self):
        with self.assertRaises(NoReverseMatch):
            reverse("studio:index")
        self.assertEqual(self.client.get("/studio/").status_code, 404)

    @override_settings(ALLOWED_HOSTS=["studio.cosound.ca"])
    def test_the_studio_host_serves_the_main_site(self):
        response = self.client.get("/", HTTP_HOST="studio.cosound.ca")
        self.assertEqual(response.status_code, 200)


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
        self.assertContains(response, reverse("library:create_sound"))

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
    def test_the_change_page_records_the_loop_check(self):
        admin_user = get_user_model().objects.create_superuser(
            username="staff", email="staff@example.com", password="pw"
        )
        sound = make_sound("Baked", seamless=True, loudness_lufs=-20.0, loop_crossfade=0.5)
        self.client.force_login(admin_user)

        response = self.client.get(reverse("admin:core_sound_change", args=[sound.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Loop check")
        self.assertContains(response, "-20.0")

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
