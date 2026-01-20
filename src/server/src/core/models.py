import datetime
import secrets
from typing import List
from datetime import datetime, timezone
from django.db import models as db_models
from pydantic import BaseModel, Field
from pgvector.django import VectorField
from django_pydantic_field import SchemaField
from django.contrib.auth.models import AbstractUser
from django.utils.module_loading import import_string

from config import settings
from core.classify import SoundClassifier


class User(AbstractUser):  # Database Class

    email = db_models.EmailField(unique=True)
    username = db_models.CharField(max_length=255, unique=True)
    created_at = db_models.DateTimeField(auto_now_add=True)
    updated_at = db_models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]


class PlayerAccount(db_models.Model):  # Database Class

    manager = db_models.ForeignKey(User, on_delete=db_models.CASCADE)
    name = db_models.CharField(max_length=255)
    bio = db_models.TextField(blank=True)
    created_at = db_models.DateTimeField(auto_now_add=True)
    updated_at = db_models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


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
    features = VectorField(
        null=True,
        dimensions=settings.COSOUND_SOUND_CLASSIFICATION_DIM,
    )
    created_at = db_models.DateTimeField(auto_now_add=True)
    updated_at = db_models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.features:
            classifier_path = settings.COSOUND_SOUND_CLASSIFICATION
            try:
                classifier: SoundClassifier = import_string(classifier_path)
                self.features = classifier.classify()
            except ImportError as e:
                raise ImportError(
                    f"Cosound Core: Could not import sound classifier '{classifier_path}': {e}"
                )
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


class Player(db_models.Model):  # Database Class

    library = db_models.ManyToManyField(Sound, blank=True)
    playing = SchemaField(schema=Cosound, default=Cosound())
    account = db_models.ForeignKey(PlayerAccount, on_delete=db_models.CASCADE)
    token = db_models.CharField(max_length=64, unique=True, editable=False)
    name = db_models.CharField(max_length=255)

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
