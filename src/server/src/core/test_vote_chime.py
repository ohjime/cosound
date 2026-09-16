import io
import json
import struct
import tempfile
import threading
import wave
from base64 import b64encode
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import (
    IntegrityError,
    close_old_connections,
    connection,
    connections,
    transaction,
)
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from django_file_form.models import TemporaryUploadedFile

from core.models import PlayerProgram, Manager, Player, Post, Sound


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}


@override_settings(STORAGES=TEST_STORAGES, MEDIA_URL="/media/")
class VoteChimeModelAndAdminTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="vote-chime-admin",
            email="vote-chime-admin@example.com",
            password="pw",
        )
        self.manager = Manager.objects.create(
            user=self.admin,
            name="Vote chime manager",
        )
        self.player = Player.objects.create(
            manager=self.manager,
            name="Vote chime player",
        )
        self.sound = Sound.objects.create(
            title="Collection sound",
            file="sounds/collection.wav",
            embeddings=[0.0] * 5,
        )
        self.player.program.collection.add(self.sound)

    @staticmethod
    def wav_bytes(*, seconds=0.05, sample=1000, sample_rate=8_000):
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            frame_count = round(seconds * sample_rate)
            audio.writeframes(struct.pack("<h", sample) * frame_count)
        return output.getvalue()

    @staticmethod
    def antiphase_wav_bytes(*, seconds=0.05, sample_rate=8_000):
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            frame_count = round(seconds * sample_rate)
            audio.writeframes(struct.pack("<hh", 1000, -1000) * frame_count)
        return output.getvalue()

    @classmethod
    def upload(cls, contents=None, *, filename="tap.wav"):
        return SimpleUploadedFile(
            filename,
            contents if contents is not None else cls.wav_bytes(),
            content_type="audio/wav",
        )

    def admin_fields(self, **overrides):
        post = self.player.program
        return {
            "post": post.post_id,
            "collection": [self.sound.pk],
            "chime_volume": post.chime_volume,
            "algorithm_refresh_interval_seconds": post.algorithm_refresh_interval_seconds,
            "algorithm_active_listener_minutes": post.algorithm_active_listener_minutes,
            "algorithm_sleep_after_minutes": post.algorithm_sleep_after_minutes,
            "algorithm_min_layers": post.algorithm_min_layers,
            "algorithm_max_layers": post.algorithm_max_layers,
            "algorithm_minimum_hold_seconds": post.algorithm_minimum_hold_seconds,
            "algorithm_maximum_stay_seconds": (
                post.algorithm_maximum_stay_seconds or ""
            ),
            "algorithm_disagreement_penalty": post.algorithm_disagreement_penalty,
            "algorithm_exploration_probability": post.algorithm_exploration_probability,
            "algorithm_exploration_size": post.algorithm_exploration_size,
            "baseline": post.baseline_id or "",
            **overrides,
        }

    def test_same_named_replacement_gets_a_new_storage_key_and_version(self):
        post = self.player.program
        post.chime.save(
            "tap.wav",
            self.upload(self.wav_bytes(sample=1000)),
        )
        first_name = post.chime.name
        first_version = post.chime_version

        post.chime.save(
            "tap.wav",
            self.upload(self.wav_bytes(sample=2000)),
        )
        second_name = post.chime.name
        second_version = post.chime_version

        self.assertRegex(first_name, r"^chimes/[0-9a-f]{32}\.wav$")
        self.assertRegex(second_name, r"^chimes/[0-9a-f]{32}\.wav$")
        self.assertNotEqual(first_name, second_name)
        self.assertNotEqual(first_version, second_version)

    def test_program_admin_exposes_and_persists_the_chime_upload(self):
        self.client.force_login(self.admin)
        change_url = reverse(
            "admin:core_playerprogram_change",
            args=[self.player.program_id],
        )

        response = self.client.get(change_url)

        self.assertContains(response, 'id="id_chime"')
        self.assertContains(
            response,
            'accept=".wav,.flac,.ogg,.mp3,.aif,.aiff"',
        )
        self.assertContains(response, "Maximum 5 seconds and 5 MB")

        response = self.client.post(
            change_url,
            self.admin_fields(chime=self.upload()),
        )

        self.assertEqual(response.status_code, 302)
        self.player.program.refresh_from_db()
        self.assertRegex(
            self.player.program.chime.name,
            r"^chimes/[0-9a-f]{32}\.wav$",
        )
        self.assertTrue(self.player.program.chime_version)
        with self.player.program.chime.open("rb") as saved:
            self.assertEqual(saved.read(), self.wav_bytes())

        response = self.client.get(change_url)
        self.assertContains(response, "<audio controls")
        self.assertContains(response, self.player.program.chime.url)

        storage = self.player.program.chime.storage
        first_name = self.player.program.chime.name
        first_version = self.player.program.chime_version
        replacement = self.wav_bytes(sample=2000)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                change_url,
                self.admin_fields(chime=self.upload(replacement)),
            )
        self.assertEqual(response.status_code, 302)
        self.player.program.refresh_from_db()
        self.assertNotEqual(self.player.program.chime_version, first_version)
        self.assertFalse(storage.exists(first_name))
        with self.player.program.chime.open("rb") as saved:
            self.assertEqual(saved.read(), replacement)

        second_name = self.player.program.chime.name
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                change_url,
                self.admin_fields(**{"chime-uploads": "[]"}),
            )
        self.assertEqual(response.status_code, 302)
        self.player.program.refresh_from_db()
        self.assertFalse(storage.exists(second_name))
        self.assertFalse(self.player.program.chime)
        self.assertEqual(self.player.program.chime_version, "")

    def test_chime_volume_defaults_and_is_bounded_to_the_zero_to_one_range(self):
        program = self.player.program
        self.assertEqual(program.chime_volume, settings.COSOUND_CHIME_VOLUME)

        for value in (-0.01, 1.01):
            with self.subTest(value=value):
                program.chime_volume = value
                with self.assertRaises(ValidationError) as raised:
                    program.full_clean()
                self.assertIn("chime_volume", raised.exception.message_dict)

        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                program.chime_volume = value
                with self.assertRaises(ValidationError) as raised:
                    program.full_clean()
                self.assertIn("chime_volume", raised.exception.message_dict)

        program.chime_volume = 0.0
        program.full_clean()
        program.save(update_fields=["chime_volume"])
        program.refresh_from_db()
        self.assertEqual(program.chime_volume, 0.0)

    def test_database_constraint_rejects_a_volume_outside_the_range(self):
        for value in (-0.5, 2.0):
            with self.subTest(value=value), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    PlayerProgram.objects.filter(pk=self.player.program_id).update(
                        chime_volume=value
                    )

    def test_invalid_oversized_overlong_and_silent_chimes_are_rejected(self):
        invalid_uploads = {
            "malformed": self.upload(b"not audio"),
            "overlong": self.upload(self.wav_bytes(seconds=5.01)),
            "silent": self.upload(self.wav_bytes(sample=0)),
            "silent after downmix": self.upload(self.antiphase_wav_bytes()),
            "unsupported": self.upload(filename="tap.txt"),
            "oversized": self.upload(b"x" * (5 * 1024 * 1024 + 1)),
        }

        for reason, upload in invalid_uploads.items():
            with self.subTest(reason=reason):
                self.player.program.chime = upload
                with self.assertRaises(ValidationError):
                    self.player.program.full_clean()

    def test_unchanged_committed_chime_is_not_downloaded_for_validation(self):
        self.player.program.chime = "chimes/already-validated.wav"
        self.assertTrue(self.player.program.chime._committed)

        with patch.object(
            self.player.program.chime.storage,
            "open",
            side_effect=AssertionError("existing media should not be reopened"),
        ):
            self.player.program.full_clean()

    def test_stale_full_save_preserves_a_concurrent_chime_replacement(self):
        post = self.player.program
        post.chime = self.upload(self.wav_bytes(sample=500))
        post.save(update_fields=["chime"])
        first = type(post).objects.get(pk=post.pk)
        stale = type(post).objects.get(pk=post.pk)
        original_name = first.chime.name

        first.chime = self.upload(self.wav_bytes(sample=2000))
        with self.captureOnCommitCallbacks(execute=True):
            first.save(update_fields=["chime"])
        replacement_name = first.chime.name
        self.assertFalse(first.chime.storage.exists(original_name))

        with self.captureOnCommitCallbacks(execute=True):
            stale.save()

        stale.refresh_from_db()
        self.assertEqual(stale.chime.name, replacement_name)
        self.assertTrue(stale.chime.storage.exists(replacement_name))

    def test_generator_update_fields_are_not_consumed_by_chime_locking(self):
        post = self.player.program
        replacement_post = Post.objects.create(
            title="Replacement writing",
            composer=self.admin,
        )
        post.post = replacement_post
        post.chime = self.upload()
        post.save(update_fields=(name for name in ["post", "chime"]))

        post.refresh_from_db()
        self.assertEqual(post.post_id, replacement_post.pk)
        first_chime = post.chime.name
        self.assertTrue(first_chime)

        final_post = Post.objects.create(title="Final writing", composer=self.admin)
        post.post = final_post
        post.save(update_fields=(name for name in ["post"]))

        post.refresh_from_db()
        self.assertEqual(post.post_id, final_post.pk)
        self.assertEqual(post.chime.name, first_chime)

    def test_generator_partial_refresh_updates_the_loaded_chime_snapshot(self):
        post = self.player.program
        post.chime = self.upload()
        post.save(update_fields=["chime"])
        stale = type(post).objects.get(pk=post.pk)
        type(post).objects.filter(pk=post.pk).update(
            chime="chimes/refreshed.wav"
        )

        stale.refresh_from_db(fields=(name for name in ["chime"]))
        self.assertEqual(stale.chime.name, "chimes/refreshed.wav")
        type(post).objects.filter(pk=post.pk).update(
            chime="chimes/concurrent.wav"
        )
        stale.save()

        stale.refresh_from_db()
        self.assertEqual(stale.chime.name, "chimes/concurrent.wav")


@override_settings(STORAGES=TEST_STORAGES, MEDIA_URL="/media/")
class VoteChimeUploadRouteTests(TestCase):
    """Cover the route the browser actually takes to deliver a chime.

    The admin form posts a placeholder, not the bytes: django-file-form uploads
    the file first and swaps the real file in while the form binds. Every other
    chime test hands Django a SimpleUploadedFile directly, which skips that
    whole exchange -- so it kept passing while production could not upload a
    chime at all.
    """

    def setUp(self):
        # Stage uploads outside the checkout. settings.py creates this directory
        # for the configured MEDIA_ROOT; redirecting MEDIA_ROOT moves it.
        staging = tempfile.TemporaryDirectory()
        self.addCleanup(staging.cleanup)
        Path(staging.name, settings.FILE_FORM_UPLOAD_DIR).mkdir(parents=True)
        media_root = override_settings(MEDIA_ROOT=staging.name)
        media_root.enable()
        self.addCleanup(media_root.disable)

        self.admin = get_user_model().objects.create_superuser(
            username="chime-upload-admin",
            email="chime-upload-admin@example.com",
            password="pw",
        )
        manager = Manager.objects.create(user=self.admin, name="Upload manager")
        self.player = Player.objects.create(manager=manager, name="Upload player")
        self.client.force_login(self.admin)

    def tus_upload(self, contents, *, filename="tap.wav", form_id, field="chime"):
        """Drive the real TUS exchange: start, then send the bytes."""
        metadata = ",".join(
            f"{key} {b64encode(value.encode()).decode()}"
            for key, value in (
                ("filename", filename),
                ("fieldName", field),
                ("formId", form_id),
            )
        )
        started = self.client.post(
            reverse("tus_upload"),
            headers={
                "tus-resumable": "1.0.0",
                "upload-length": str(len(contents)),
                "upload-metadata": metadata,
            },
        )
        self.assertEqual(started.status_code, 201)
        resource_id = started.headers["ResourceId"]

        sent = self.client.patch(
            reverse("tus_upload_chunks", args=[resource_id]),
            data=contents,
            content_type="application/offset+octet-stream",
            headers={"tus-resumable": "1.0.0", "upload-offset": "0"},
        )
        self.assertEqual(sent.status_code, 204)
        return resource_id

    def test_the_chime_field_uploads_to_this_origin_not_straight_to_s3(self):
        # A direct-to-S3 upload needs the bucket to grant CORS to the admin's
        # origin. It did not, so the browser's PUT was blocked and the upload
        # died after signing the first part -- the form itself never saw a file.
        response = self.client.get(
            reverse("admin:core_playerprogram_change", args=[self.player.program_id])
        )

        self.assertContains(response, f'value="{reverse("tus_upload")}"')
        self.assertNotContains(response, 'name="s3_upload_dir"')
        self.assertNotContains(response, reverse("s3_upload"))

    def test_a_chime_uploaded_the_way_the_browser_sends_it_is_stored(self):
        program = self.player.program
        contents = VoteChimeModelAndAdminTests.wav_bytes()
        form_id = "6cbda592-fa89-4cf7-93e2-c70cc4ed1252"
        resource_id = self.tus_upload(contents, form_id=form_id)

        response = self.client.post(
            reverse("admin:core_playerprogram_change", args=[program.pk]),
            {
                "post": program.post_id,
                "collection": [],
                "algorithm_refresh_interval_seconds": program.algorithm_refresh_interval_seconds,
                "algorithm_active_listener_minutes": program.algorithm_active_listener_minutes,
                "algorithm_sleep_after_minutes": program.algorithm_sleep_after_minutes,
                "algorithm_min_layers": program.algorithm_min_layers,
                "algorithm_max_layers": program.algorithm_max_layers,
                "algorithm_minimum_hold_seconds": program.algorithm_minimum_hold_seconds,
                "algorithm_maximum_stay_seconds": (
                    program.algorithm_maximum_stay_seconds or ""
                ),
                "algorithm_disagreement_penalty": program.algorithm_disagreement_penalty,
                "algorithm_exploration_probability": program.algorithm_exploration_probability,
                "algorithm_exploration_size": program.algorithm_exploration_size,
                "chime_volume": program.chime_volume,
                "baseline": "",
                "form_id": form_id,
                # What the uploader leaves behind in place of the bytes.
                "chime-uploads": json.dumps(
                    [
                        {
                            "id": resource_id,
                            "name": "tap.wav",
                            "size": len(contents),
                            "type": "placeholder",
                        }
                    ]
                ),
                "chime-metadata": "{}",
            },
        )

        self.assertEqual(response.status_code, 302)
        program.refresh_from_db()
        self.assertRegex(program.chime.name, r"^chimes/[0-9a-f]{32}\.wav$")
        with program.chime.open("rb") as saved:
            self.assertEqual(saved.read(), contents)
        # The staged copy is handed off, not left behind.
        self.assertFalse(TemporaryUploadedFile.objects.filter(form_id=form_id).exists())


@override_settings(STORAGES=TEST_STORAGES, MEDIA_URL="/media/")
class VoteChimeInvalidationTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="vote-chime-events",
            email="vote-chime-events@example.com",
        )
        manager = Manager.objects.create(user=user, name="Events manager")
        self.player = Player.objects.create(manager=manager, name="Listening room")
        self.other = Player.objects.create(manager=manager, name="Other room")

    @patch("core.player_events.publish_player_changes")
    def test_chime_change_notifies_only_the_attached_player_after_commit(
        self,
        publish,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                self.player.program.chime = "chimes/updated.wav"
                self.player.program.save(update_fields=["chime"])
                publish.assert_not_called()
            publish.assert_not_called()

        publish.assert_called_once_with((self.player.pk,))

    @patch("core.player_events.publish_player_changes")
    def test_rolled_back_chime_change_does_not_notify(self, publish):
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    self.player.program.chime = "chimes/rolled-back.wav"
                    self.player.program.save(update_fields=["chime"])
                    raise RuntimeError("roll back the chime")
            except RuntimeError:
                pass

        publish.assert_not_called()
        self.player.program.refresh_from_db()
        self.assertFalse(self.player.program.chime)

    @patch("core.player_events.publish_player_changes")
    def test_unchanged_chime_save_does_not_notify(self, publish):
        type(self.player.program).objects.filter(pk=self.player.program_id).update(
            chime="chimes/unchanged.wav"
        )
        self.player.program.refresh_from_db()

        with self.captureOnCommitCallbacks(execute=True):
            self.player.program.save(update_fields=["chime"])

        publish.assert_not_called()


@override_settings(STORAGES=TEST_STORAGES, MEDIA_URL="/media/")
class VoteChimeConcurrencyTests(TransactionTestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="vote-chime-concurrency",
            email="vote-chime-concurrency@example.com",
        )
        post = Post.objects.create(title="Concurrent post", composer=user)
        self.program = PlayerProgram.objects.create(post=post)

    def test_concurrent_replacements_leave_only_the_winning_file(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency is exercised on PostgreSQL.")

        initial = VoteChimeModelAndAdminTests.upload(
            VoteChimeModelAndAdminTests.wav_bytes(sample=500)
        )
        self.program.chime = initial
        self.program.save(update_fields=["chime"])
        initial_name = self.program.chime.name
        storage = self.program.chime.storage
        start = threading.Barrier(2)

        def replace(sample):
            close_old_connections()
            try:
                program = PlayerProgram.objects.get(pk=self.program.pk)
                program.chime = VoteChimeModelAndAdminTests.upload(
                    VoteChimeModelAndAdminTests.wav_bytes(sample=sample)
                )
                start.wait(timeout=5)
                program.save(update_fields=["chime"])
                return program.chime.name
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            uploaded_names = set(executor.map(replace, (1000, 2000)))

        self.program.refresh_from_db()
        winning_name = self.program.chime.name
        self.assertIn(winning_name, uploaded_names)
        self.assertTrue(storage.exists(winning_name))
        self.assertFalse(storage.exists(initial_name))
        for losing_name in uploaded_names - {winning_name}:
            self.assertFalse(storage.exists(losing_name))
