"""Permission-aware routes for django-file-form uploads."""

from django.contrib.admin.views.decorators import staff_member_required
from django.urls import include, path
from django_file_form.s3_multipart import views as s3_views


urlpatterns = [
    # TUS performs its own FILE_FORM_MUST_LOGIN permission check and is used by
    # authenticated, non-staff profile uploads.
    path("upload/", include("django_file_form.tus.urls")),
    # django-file-form's S3 views do not run that check. These endpoints issue
    # signed multipart requests and are only used by admin forms, so protect
    # every stage before it can reach S3.
    path(
        "s3upload/",
        staff_member_required(s3_views.create_upload),
        name="s3_upload",
    ),
    path(
        "s3upload/<upload_id>/",
        staff_member_required(s3_views.abort_upload),
        name="get_parts_or_abort_upload",
    ),
    path(
        "s3upload/<upload_id>/<int:part_number>",
        staff_member_required(s3_views.sign_upload_part),
        name="sign_part_upload",
    ),
    path(
        "s3upload/<upload_id>/complete",
        staff_member_required(s3_views.complete_upload),
        name="complete_multipart_upload",
    ),
]
