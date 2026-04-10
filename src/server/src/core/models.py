import datetime
import secrets
from typing import List
from datetime import datetime, timezone
from django.db import models as db_models
from pydantic import BaseModel, Field
from pgvector.django import VectorField
from django_pydantic_field import SchemaField
from django.contrib.auth.models import AbstractUser
from core.utils import (
    _get_sound_dimension,
    _get_sound_classifier,
    _get_listener_dimension,
    _get_listener_classifier,
)


class SoundType(db_models.TextChoices):  # Data Class

    SOUNDSCAPE = "Soundscape"
    INSTRUMENTAL = "Instrumental"


class SoundLayer(BaseModel):  # Data Class

    sound_id: str
    sound_file: str
    sound_title: str = Field(max_length=100)
    sound_artist: str
    sound_type: str
    sound_gain: float = Field(default=1.0, ge=0.0, le=1.0)


class Cosound(BaseModel):  # Data Class

    meta: dict = Field(default_factory=dict)
    layers: List[SoundLayer] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Sound(db_models.Model):  # Database Class

    file = db_models.FileField(upload_to="sounds/")
    title = db_models.CharField(max_length=255)
    artist = db_models.CharField(max_length=255)
    type = db_models.CharField(choices=SoundType.choices)
    art = db_models.ImageField(upload_to="sound_arts/", blank=True, null=True)
    flavor = db_models.TextField(blank=True, null=True)
    embeddings = VectorField(
        null=True,
        dimensions=_get_sound_dimension(),
    )
    created_at = db_models.DateTimeField(auto_now_add=True)
    updated_at = db_models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.embeddings:
            classifier = _get_sound_classifier()
            self.embeddings = classifier(self.pk)
        super().save(*args, **kwargs)

    def asLayer(self, with_gain: float = 1.0) -> SoundLayer:
        return SoundLayer(
            sound_id=str(self.pk),
            sound_file=self.file.url,
            sound_title=self.title,
            sound_artist=self.artist,
            sound_type=self.type,
            sound_gain=with_gain,
        )


class User(AbstractUser):  # Database Class

    email = db_models.EmailField(unique=True)
    username = db_models.CharField(max_length=255, unique=True)
    avatar = db_models.ImageField(upload_to="avatars/", blank=True, null=True)
    created_at = db_models.DateTimeField(auto_now_add=True)
    updated_at = db_models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]


class Manager(db_models.Model):  # Database Class

    user = db_models.ForeignKey(User, on_delete=db_models.CASCADE)
    name = db_models.CharField(max_length=255)
    logo = db_models.ImageField(upload_to="logos/", blank=True, null=True)
    bio = db_models.TextField(blank=True)
    created_at = db_models.DateTimeField(auto_now_add=True)
    updated_at = db_models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Player(db_models.Model):  # Database Class

    library = db_models.ManyToManyField(Sound, blank=True)
    playing: Cosound = SchemaField(default=Cosound)
    account = db_models.ForeignKey(Manager, on_delete=db_models.CASCADE)
    token = db_models.CharField(max_length=64, unique=True, editable=False)
    name = db_models.CharField(max_length=255)
    photo = db_models.ImageField(upload_to="photos/", blank=True, null=True)
    bio = db_models.TextField(blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def summary(self):
        string = ""
        for i, layer in enumerate(self.playing.layers):
            sound = Sound.objects.get(id=layer.sound_id)
            string += f"\t  {layer.sound_type} Layer {i+1}: {sound.title}\n"
            string += f"\t\t-> Global Gain: {layer.sound_gain:.2f}\n"
        string.strip()
        return string


class Listener(db_models.Model):  # Database Class

    user = db_models.OneToOneField(
        User,
        on_delete=db_models.CASCADE,
    )
    embeddings = VectorField(
        null=True,
        dimensions=_get_listener_dimension(),
    )
    created_at = db_models.DateTimeField(auto_now_add=True)
    updated_at = db_models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.embeddings:
            classifier = _get_listener_classifier()
            self.embeddings = classifier(self.pk)
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.user)
