from django_file_form.model_admin import FileFormAdmin
from django_file_form.forms import FileFormMixin, UploadedFileField
from django import forms
from django.forms import ModelForm
from taggit.models import Tag
from unfold.widgets import UnfoldAdminSelect2MultipleWidget
from core.widgets import AudioUploadWidget
from core.models import Comment, PlayerProgram, Post, Sound, User
from core.fonts import article_font_choices
from core.post_widgets import AuthorsWidget, EasyMDEWidget


class SoundForm(FileFormMixin, ModelForm):
    file = UploadedFileField(widget=AudioUploadWidget)
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        required=False,
        widget=UnfoldAdminSelect2MultipleWidget,
    )

    class Meta:
        model = Sound
        fields = ["file", "title", "artist", "set", "art", "flavor", "tags"]

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


class PostForm(forms.ModelForm):
    font_family = forms.ChoiceField(
        label="Post font",
        required=False,
        help_text="Used for selected elements in the article layout.",
    )
    authors = forms.JSONField(
        required=False,
        initial=list,
        help_text=(
            "Add each author and their role. The URL is optional and can go "
            "straight to the author's own page — their site, a profile, a "
            "label — rather than anything hosted here. The credit opens it in "
            "a new tab, so the post keeps playing behind it."
        ),
        widget=AuthorsWidget,
    )

    class Meta:
        model = Post
        fields = "__all__"
        widgets = {"article": EasyMDEWidget()}
        help_texts = {
            "article": (
                "Markdown. External links open in a new tab. In Explore, link "
                "to a featured layer using [the rain](#layer-2) or "
                "[the rain](#layer-rain-on-tin). Layer links select that layer "
                "in the fixed mix; links without a matching layer render as text."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = article_font_choices()
        selected_font = (
            self.data.get("font_family")
            if self.is_bound
            else getattr(self.instance, "font_family", "")
        )
        if selected_font and selected_font not in dict(choices):
            choices.append(
                (
                    selected_font,
                    f"{selected_font} (missing — using Tailwind Sans)",
                )
            )
        self.fields["font_family"].choices = choices

    def clean_authors(self):
        return self.cleaned_data.get("authors") or []


class PlayerProgramForm(FileFormMixin, forms.ModelForm):
    chime = UploadedFileField(
        required=False,
        widget=AudioUploadWidget,
        accept=".wav,.flac,.ogg,.mp3,.aif,.aiff",
        label="Vote confirmation chime",
        help_text=(
            "Maximum 5 seconds and 5 MB. Supported formats: WAV, FLAC, OGG, "
            "MP3, and AIFF."
        ),
    )

    class Meta:
        model = PlayerProgram
        fields = [
            "post",
            "collection",
            "chime",
            "algorithm_refresh_interval_seconds",
            "algorithm_active_listener_minutes",
            "algorithm_sleep_after_minutes",
            "algorithm_min_layers",
            "algorithm_max_layers",
            "algorithm_minimum_hold_seconds",
            "algorithm_maximum_stay_seconds",
            "algorithm_disagreement_penalty",
            "algorithm_exploration_probability",
            "algorithm_exploration_size",
            "baseline",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, s3_upload_dir="chimes", **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        collection = cleaned_data.get("collection")
        if collection is not None:
            self.instance._submitted_collection_sound_ids = {
                sound.pk for sound in collection
            }
        return cleaned_data


class CommentForm(forms.ModelForm):
    body = forms.CharField(
        max_length=2000,
        error_messages={"required": "Write a comment before posting."},
        widget=forms.Textarea(
            attrs={
                "class": "textarea textarea-bordered h-28 w-full resize-y",
                "maxlength": 2000,
                "placeholder": "Share what you heard, noticed, or felt…",
                "required": True,
                "aria-label": "Your comment",
            }
        ),
    )

    class Meta:
        model = Comment
        fields = ["body"]

    def clean_body(self):
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError("Write a comment before posting.")
        return body
