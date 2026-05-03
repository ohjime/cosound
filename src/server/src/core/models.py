import datetime
import hashlib
import secrets
from decimal import ROUND_UP, Decimal
from typing import List
from datetime import datetime, timezone
from django.db import models as DjangoDB, transaction
from pydantic import BaseModel, Field
from pgvector.django import VectorField
from django_pydantic_field import SchemaField
from django.contrib.auth.models import AbstractUser
from taggit.managers import TaggableManager
from core.utils import (
    _get_sound_dimension,
    _get_sound_classifier,
    generate_layers_string,
)
from core.predict import Prediction


class Sound(DjangoDB.Model):
    file = DjangoDB.FileField(upload_to="sounds/")
    title = DjangoDB.CharField(max_length=255)
    artist = DjangoDB.CharField(max_length=255)
    tags = TaggableManager(blank=True)
    art = DjangoDB.ImageField(
        upload_to="sound_arts/", blank=True, null=True, max_length=255
    )
    flavor = DjangoDB.TextField(blank=True, null=True, max_length=200)
    embeddings = VectorField(null=True, dimensions=_get_sound_dimension())
    created_at = DjangoDB.DateTimeField(auto_now_add=True)
    updated_at = DjangoDB.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.embeddings is None:
            classifier = _get_sound_classifier()
            self.embeddings = classifier(self.pk)
        super().save(*args, **kwargs)

    def asLayer(self, with_gain=1.0):
        return {
            "sound_id": self.pk,
            "sound_file": self.file.url,
            "sound_gain": with_gain,
            "sound_title": self.title,
            "sound_artist": self.artist,
        }


class SoundLayer(DjangoDB.Model):
    sound = DjangoDB.ForeignKey(Sound, on_delete=DjangoDB.CASCADE)
    mix = DjangoDB.ForeignKey("Cosound", on_delete=DjangoDB.CASCADE)
    gain = DjangoDB.DecimalField(max_digits=3, decimal_places=2)

    def __str__(self):
        return f"{self.sound.pk}@{self.gain}"


class Cosound(DjangoDB.Model):

    layers = DjangoDB.ManyToManyField(Sound, through=SoundLayer)
    hashset = DjangoDB.CharField(max_length=64, editable=False, db_index=True)
    created_at = DjangoDB.DateTimeField(auto_now_add=True)
    hashid = DjangoDB.CharField(
        max_length=64, unique=True, editable=False, db_index=True
    )

    @classmethod
    def normalize_layers(cls, layers):
        normalized = []
        for sound_id, gain in layers:
            gain = Decimal(str(gain))
            rounded = (gain * 2).quantize(Decimal("0.1"), rounding=ROUND_UP) / 2
            normalized.append((sound_id, rounded))
        normalized.sort(key=lambda t: t[0])
        return normalized

    @staticmethod
    def compute_hashid(layers):
        normalized = Cosound.normalize_layers(layers)
        key = generate_layers_string(normalized)
        hashid = hashlib.sha256(key.encode()).hexdigest()
        return hashid

    @staticmethod
    def compute_hashset(layers):
        normalized = Cosound.normalize_layers(layers)
        key = generate_layers_string(normalized, with_gain=False)
        hashset = hashlib.sha256(key.encode()).hexdigest()
        return hashset

    @classmethod
    def get_or_create_from_layers(cls, layers):
        hashid = cls.compute_hashid(layers)
        hashset = cls.compute_hashset(layers)
        normalized = cls.normalize_layers(layers)
        with transaction.atomic():
            cosound, created = cls.objects.get_or_create(
                hashid=hashid, defaults={"hashset": hashset}
            )
            if created:
                SoundLayer.objects.bulk_create(
                    [
                        SoundLayer(sound_id=sid, mix=cosound, gain=g)
                        for sid, g in normalized
                    ]
                )
        return cosound

    @classmethod
    def with_sound_set(cls, sound_ids):
        """Cosounds whose layer sound set exactly matches `sound_ids` (gain-agnostic)."""
        ids = list({int(sid) for sid in sound_ids})
        if not ids:
            return cls.objects.none()
        return cls.objects.filter(hashset=cls.compute_hashset(ids))

    def __str__(self):
        layers = []
        for layer in self.soundlayer_set.all():  # type: ignore
            layers.append(tuple([layer.sound.pk, layer.gain]))
        return generate_layers_string(layers)


class User(AbstractUser):
    email = DjangoDB.EmailField(unique=True)
    username = DjangoDB.CharField(max_length=255, unique=True)
    avatar = DjangoDB.ImageField(
        upload_to="avatars/", blank=True, null=True, max_length=255
    )
    created_at = DjangoDB.DateTimeField(auto_now_add=True)
    updated_at = DjangoDB.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]


class Listener(DjangoDB.Model):
    user = DjangoDB.OneToOneField(User, on_delete=DjangoDB.CASCADE)
    collection = DjangoDB.ManyToManyField(Sound, blank=True, related_name="saved_by")
    created_at = DjangoDB.DateTimeField(auto_now_add=True)
    updated_at = DjangoDB.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.user)


class Manager(DjangoDB.Model):
    user = DjangoDB.ForeignKey(User, on_delete=DjangoDB.CASCADE)
    name = DjangoDB.CharField(max_length=255)
    logo = DjangoDB.ImageField(
        upload_to="logos/", blank=True, null=True, max_length=255
    )
    bio = DjangoDB.TextField(blank=True)
    created_at = DjangoDB.DateTimeField(auto_now_add=True)
    updated_at = DjangoDB.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Player(DjangoDB.Model):
    sounds = DjangoDB.ManyToManyField(Sound, blank=True)
    playing: Prediction = SchemaField(default=Prediction)
    manager = DjangoDB.ForeignKey(Manager, on_delete=DjangoDB.CASCADE)
    token = DjangoDB.CharField(max_length=64, unique=True, editable=False)
    name = DjangoDB.CharField(max_length=255)
    photo = DjangoDB.ImageField(
        upload_to="photos/", blank=True, null=True, max_length=255
    )
    bio = DjangoDB.TextField(blank=True, max_length=200)
    location = DjangoDB.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_hex(32)
        super().save(*args, **kwargs)
