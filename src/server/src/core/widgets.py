from django_file_form.widgets import UploadWidget


class AudioUploadWidget(UploadWidget):
    """Custom upload widget that displays an audio player for existing files."""

    template_name = "admin/audio_upload_widget.html"
