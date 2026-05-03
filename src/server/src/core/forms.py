from django_file_form.model_admin import FileFormAdmin
from django_file_form.forms import FileFormMixin, UploadedFileField
from django import forms
from django.forms import ModelForm
from taggit.models import Tag
from unfold.widgets import UnfoldAdminSelect2MultipleWidget
from core.widgets import AudioUploadWidget
from core.models import Sound, User


class SoundForm(FileFormMixin, ModelForm):
    file = UploadedFileField(widget=AudioUploadWidget)
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        widget=UnfoldAdminSelect2MultipleWidget,
    )

    class Meta:
        model = Sound
        fields = ["file", "title", "artist", "art", "flavor", "tags"]

    readonly_fields = ["timestamp"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, s3_upload_dir="sounds", **kwargs)
        if self.instance.pk:
            self.fields["tags"].initial = self.instance.tags.all()

    def _save_m2m(self):
        super()._save_m2m()
        self.instance.tags.set(self.cleaned_data.get("tags", []))


class UserAvatarForm(FileFormMixin, ModelForm):
    avatar = UploadedFileField(required=False)

    class Meta:
        model = User
        fields = ["avatar"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, s3_upload_dir="avatars", **kwargs)
