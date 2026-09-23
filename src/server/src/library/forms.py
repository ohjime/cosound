from functools import reduce
from operator import or_

from django import forms
from django.db.models import Q
from taggit.models import Tag

from core.audio import HOUSE_LOUDNESS_LUFS, LOUDNESS_NUDGE_LU, MIN_REGION_SECONDS
from core.validators import validate_sound


ARTWORK_MAX_BYTES = 10 * 1024 * 1024


class NewSoundForm(forms.Form):
    """A new sound as the LIBRARY tab's card posts it on save.

    The words the card let the artist write, the two files it held in the tab,
    and the loop check they were heard through: the crop, the crossfade folded
    into the seam, and the loudness to level to, with the engine's reading of
    the cropped region. core.audio.bake_sound makes the last three permanent.

    Tags arrive one per line. A name that matches an existing tag (whatever its
    case) becomes that tag; any other is a tag the artist typed into the card
    and pressed Enter on, and is created with the sound when the mix is saved.
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
        names = {}
        for raw in self.cleaned_data["tags"].split("\n"):
            name = raw.strip()
            if name:
                names.setdefault(name.lower(), name)
        if not names:
            return []
        limit = Tag._meta.get_field("name").max_length
        if any(len(name) > limit for name in names.values()):
            raise forms.ValidationError(f"A tag can be at most {limit} characters.")
        # Reuse the existing spelling so "rain" lands on "Rain" rather than
        # beside it; taggit creates whatever is left when the sound is tagged.
        existing = Tag.objects.filter(reduce(or_, (Q(name__iexact=n) for n in names.values())))
        for tag in existing:
            names[tag.name.lower()] = tag.name
        return list(names.values())

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
