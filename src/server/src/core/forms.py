from django_file_form.model_admin import FileFormAdmin
from django_file_form.forms import FileFormMixin, UploadedFileField
from django.forms import ModelForm
from core.widgets import AudioUploadWidget
from core.models import Sound


class SoundForm(FileFormMixin, ModelForm):
    file = UploadedFileField(widget=AudioUploadWidget)

    class Meta:
        model = Sound
        fields = ["file", "title", "artist", "type"]

    readonly_fields = ["timestamp"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, s3_upload_dir="sounds", **kwargs)
