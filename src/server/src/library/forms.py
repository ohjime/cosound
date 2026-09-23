from django import forms
from django.contrib.contenttypes.models import ContentType
from taggit.models import Tag

from core.audio import HOUSE_LOUDNESS_LUFS, LOUDNESS_NUDGE_LU, MIN_REGION_SECONDS
from core.models import Sound
from core.validators import validate_sound


ARTWORK_MAX_BYTES = 10 * 1024 * 1024


class NewSoundForm(forms.Form):
    """A new sound as the LIBRARY tab's card posts it on save.

    The words the card let the artist write, the two files it held in the tab,
    and the loop check they were heard through: the crop, the crossfade folded
    into the seam, and the loudness to level to, with the engine's reading of
    the cropped region. core.audio.bake_sound makes the last three permanent.

    Tags arrive one per line and must already exist on some Sound — the card
    only ever offers those (library_tag_search), so anything else is dropped
    rather than created behind cosound's back.
    """

    file = forms.FileField(validators=[validate_sound])
    art = forms.ImageField()
    title = forms.CharField(max_length=255)
    flavor = forms.CharField(max_length=200, required=False)
    tags = forms.CharField(required=False)
    trim_start = forms.FloatField(required=False, min_value=0)
    trim_end = forms.FloatField(required=False, min_value=0)
    loop_crossfade = forms.FloatField(required=False, min_value=0)
    loudness = forms.FloatField(required=False, min_value=-120, max_value=20)
    loudness_target = forms.FloatField(
        required=False,
        min_value=HOUSE_LOUDNESS_LUFS - LOUDNESS_NUDGE_LU,
        max_value=HOUSE_LOUDNESS_LUFS + LOUDNESS_NUDGE_LU,
    )

    def clean_art(self):
        art = self.cleaned_data["art"]
        if art.size > ARTWORK_MAX_BYTES:
            raise forms.ValidationError("Artwork must be 10 MB or smaller.")
        return art

    def clean_tags(self):
        names = {n.strip() for n in self.cleaned_data["tags"].split("\n") if n.strip()}
        if not names:
            return []
        return list(
            Tag.objects.filter(
                taggit_taggeditem_items__content_type=ContentType.objects.get_for_model(Sound),
                name__in=names,
            )
            .distinct()
            .values_list("name", flat=True)
        )

    def clean(self):
        """The loop check has to describe something the file can hold.

        The crop must leave at least MIN_REGION_SECONDS, and the crossfade can
        fold at most half of what the crop kept — the engine's own ceiling, past
        which a pass's two fades would cross. Where the crop runs past the file
        is the bake's business (it stops at the end, as the engine does); here
        only the two numbers are checked against each other.
        """
        data = super().clean()
        start = data.get("trim_start") or 0.0
        end = data.get("trim_end")
        if end is not None and end - start < MIN_REGION_SECONDS:
            raise forms.ValidationError(
                f"Keep at least {MIN_REGION_SECONDS:g} seconds of the sound."
            )
        fade = data.get("loop_crossfade") or 0.0
        if end is not None and fade > (end - start) / 2:
            self.add_error("loop_crossfade", "A crossfade can fold at most half the sound.")
        data["trim_start"] = start
        data["loop_crossfade"] = fade
        if data.get("loudness_target") is None:
            data["loudness_target"] = HOUSE_LOUDNESS_LUFS
        return data
