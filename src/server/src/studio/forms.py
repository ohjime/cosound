from django import forms
from django.contrib.contenttypes.models import ContentType
from taggit.models import Tag

from core.models import Sound
from core.validators import validate_sound


ARTWORK_MAX_BYTES = 10 * 1024 * 1024


class NewSoundForm(forms.Form):
    """A new sound as the LIBRARY tab's card posts it on save.

    The same words the card let the artist write, plus the two files it held in
    the tab. Tags arrive one per line and must already exist on some Sound —
    the card only ever offers those (see studio_tag_search), so anything else
    is dropped rather than created behind cosound's back.
    """

    file = forms.FileField(validators=[validate_sound])
    art = forms.ImageField()
    title = forms.CharField(max_length=255)
    flavor = forms.CharField(max_length=200, required=False)
    tags = forms.CharField(required=False)

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
