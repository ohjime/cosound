import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class FileUploadSecurityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="upload-user",
            email="upload-user@example.com",
        )
        self.staff = get_user_model().objects.create_user(
            username="upload-staff",
            email="upload-staff@example.com",
            is_staff=True,
        )

    @staticmethod
    def requests():
        return [
            ("post", reverse("s3_upload"), {}),
            (
                "delete",
                reverse("get_parts_or_abort_upload", args=["upload-id"]),
                {"QUERY_STRING": "key=temporary.wav"},
            ),
            (
                "get",
                reverse("sign_part_upload", args=["upload-id", 1]),
                {"QUERY_STRING": "key=temporary.wav"},
            ),
            (
                "post",
                reverse("complete_multipart_upload", args=["upload-id"]),
                {"QUERY_STRING": "key=temporary.wav"},
            ),
        ]

    @patch("django_file_form.s3_multipart.views.get_client")
    def test_s3_multipart_routes_reject_anonymous_and_nonstaff_users(
        self,
        get_client,
    ):
        for authenticated in (False, True):
            if authenticated:
                self.client.force_login(self.user)
            for method, url, extra in self.requests():
                with self.subTest(authenticated=authenticated, method=method, url=url):
                    response = getattr(self.client, method)(url, **extra)
                    self.assertEqual(response.status_code, 302)
                    self.assertIn(reverse("admin:login"), response.url)
            self.client.logout()

        get_client.assert_not_called()

    def test_staff_can_start_an_s3_multipart_upload(self):
        self.client.force_login(self.staff)
        storage_client = Mock()
        storage_client.create_multipart_upload.return_value = {
            "Key": "file-form-uploads/chimes/tap.wav",
            "UploadId": "upload-id",
        }
        body = json.dumps(
            {
                "filename": "tap.wav",
                "s3UploadDir": "chimes",
                "contentType": "audio/wav",
            }
        )

        with (
            patch(
                "django_file_form.s3_multipart.views.get_client",
                return_value=storage_client,
            ),
            patch(
                "django_file_form.s3_multipart.views.get_bucket_name",
                return_value="test-bucket",
            ),
            patch(
                "django_file_form.s3_multipart.views.get_available_name",
                return_value="file-form-uploads/chimes/tap.wav",
            ),
        ):
            response = self.client.post(
                reverse("s3_upload"),
                data=body,
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "key": "file-form-uploads/chimes/tap.wav",
                "uploadId": "upload-id",
            },
        )
        storage_client.create_multipart_upload.assert_called_once_with(
            Bucket="test-bucket",
            Key="file-form-uploads/chimes/tap.wav",
            ContentType="audio/wav",
        )
