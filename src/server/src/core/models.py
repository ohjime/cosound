import hashlib
import math
import secrets
import uuid
from decimal import ROUND_UP, Decimal
from typing import List

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
    URLValidator,
)
from django.db import models as DjangoDB
from django.db import router, transaction
from django.urls import reverse
from django.utils import timezone
from django_pydantic_field import SchemaField
from pgvector.django import VectorField
from pydantic import BaseModel, Field
from taggit.managers import TaggableManager

from core.fonts import article_font_css_stack
from core.utils import (
    _get_sound_classifier,
    _get_sound_dimension,
    generate_layers_string,
    get_random_avatar_url,
)
from core.validators import validate_chime


MIN_ALGORITHM_REFRESH_SECONDS = 5
MIN_PLAYER_STATE_REFRESH_SECONDS = 5
MAX_ALGORITHM_LAYERS = 5


def chime_upload_path(instance, filename):
    """Give every chime upload a new immutable storage key.

    The original filename cannot be used as a cache version: S3 is allowed to
    overwrite an existing key, and its signed URL may change between requests.
    """
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    suffix = f".{suffix}" if suffix else ""
    return f"chimes/{uuid.uuid4().hex}{suffix}"


class SoundQuerySet(DjangoDB.QuerySet):
    def published(self):
        return self.filter(published=True)

    def visible_to(self, user):
        """Published sounds, plus the ones this user uploaded and is waiting on.

        An artist's own sound is theirs to build with from the moment it is
        created, before anyone has reviewed it; nobody else sees it until then.
        """
        if user is None or not user.is_authenticated:
            return self.published()
        return self.filter(DjangoDB.Q(published=True) | DjangoDB.Q(artist__user=user))


class Sound(DjangoDB.Model):
    objects = SoundQuerySet.as_manager()

    file = DjangoDB.FileField(upload_to="sounds/")
    title = DjangoDB.CharField(max_length=255)
    artist = DjangoDB.ForeignKey(
        "Artist",
        on_delete=DjangoDB.SET_NULL,
        null=True,
        blank=True,
        related_name="sounds",
    )
    # Optional grouping of an artist's sounds. A sound with no set is a "single".
    set = DjangoDB.ForeignKey(
        "Set",
        on_delete=DjangoDB.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="sounds",
    )
    # Legacy free-text artist, kept so the artist FK can be backfilled. Unused
    # by the app going forward; safe to drop once the migration is verified.
    artist_legacy = DjangoDB.CharField(max_length=255, blank=True, null=True)
    tags = TaggableManager(blank=True)
    art = DjangoDB.ImageField(
        upload_to="sound_arts/", blank=True, null=True, max_length=255
    )
    flavor = DjangoDB.TextField(blank=True, null=True, max_length=200)
    # Whether cosound has reviewed this sound and let it out to everyone. Only
    # staff set it, from the admin. An artist's upload starts unpublished: it
    # plays in its own artist's mixes, and nowhere else — not the picker, not
    # other listeners' saved mixes, not a player's program.
    published = DjangoDB.BooleanField(
        default=False,
        help_text=(
            "Reviewed and cleared for everyone. Unpublished sounds are heard "
            "only by the artist who uploaded them."
        ),
    )
    embeddings = VectorField(null=True, dimensions=_get_sound_dimension())
    created_at = DjangoDB.DateTimeField(auto_now_add=True)
    updated_at = DjangoDB.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def artist_name(self) -> str:
        """Display name of the artist, falling back to the legacy text."""
        if self.artist_id:
            return self.artist.name
        return self.artist_legacy or ""

    @property
    def artist_url(self) -> str:
        """The artist's own page, when they have given us one.

        Empty for a legacy credit, which is a name in a text column with no
        Artist row — and so nowhere to keep a URL — behind it. That empty
        string is what the carousel reads to decide whether pressing the name
        leaves for the artist's own site or opens our details modal instead.
        """
        if self.artist_id:
            return self.artist.url or ""
        return ""

    def save(self, *args, **kwargs):
        if self.embeddings is None:
            classifier = _get_sound_classifier()
            self.embeddings = classifier(self.pk)
        super().save(*args, **kwargs)

    def asLayer(self, with_gain=1.0):
        # Every surface that mounts a soundscape spreads this dict, so a field
        # added here reaches the library, the explore card, the swap picker and
        # the studio at once. `artist_url` rides along with the name it belongs
        # to: the two are one credit, and a layer carrying one without the
        # other is how a name comes to point at the wrong artist's site.
        return {
            "sound_id": self.pk,
            "sound_file": self.file.url,
            "sound_gain": with_gain,
            "sound_title": self.title,
            "sound_artist": self.artist_name,
            "artist_url": self.artist_url,
            # Only ever false for the artist who uploaded it — nobody else is
            # served an unpublished sound — so the card can say it is waiting.
            "published": self.published,
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

    def layering(self) -> List["SoundLayer"]:
        return list(self.soundlayer_set.select_related("sound").all())

    def as_layers(self, user=None):
        """This mix in the shape c-core-sound-player hands to the browser.

        The same dict shape library.utils.get_random_sounds builds, so any
        surface that renders the shared soundscape card can mount a stored
        cosound the way the library mounts a random one.

        `user` decides only whether each layer opens with a filled heart —
        pass the request's user wherever the card is rendered for someone, or
        leave it off and every layer reads as uncollected.
        """
        saved_ids = set()
        if user is not None and user.is_authenticated:
            listener = Listener.objects.filter(user=user).first()
            if listener is not None:
                saved_ids = set(listener.collection.values_list("id", flat=True))

        layers = self.soundlayer_set.select_related("sound__artist").prefetch_related(
            "sound__tags"
        )
        return [
            {
                **layer.sound.asLayer(with_gain=float(layer.gain)),
                "artwork_url": layer.sound.art.url if layer.sound.art else "",
                # A stored mix already carries a muted layer as gain 0, so
                # nothing here starts muted — the fader shows where it sits.
                "mute": False,
                "saved": layer.sound.pk in saved_ids,
                "flavor": layer.sound.flavor or "",
                "tags": " / ".join(layer.sound.tags.names()) or "Unknown",
            }
            for layer in layers
        ]

    def __str__(self):
        layers = []
        for layer in self.soundlayer_set.all():  # type: ignore
            layers.append(tuple([layer.sound.pk, layer.gain]))
        return generate_layers_string(layers)


class PredictionLayer(BaseModel):
    sound_id: int
    sound_gain: float = Field(default=1.0, ge=0.0, le=1.0)


class Prediction(BaseModel):
    layers: List[PredictionLayer] = Field(default_factory=list)

    @classmethod
    def new(cls) -> "Prediction":
        return cls()

    def add_layer(self, sound_id: int, gain: float = 1.0) -> None:
        self.layers.append(PredictionLayer(sound_id=sound_id, sound_gain=gain))

    def __bool__(self) -> bool:
        return bool(self.layers)

    def summary(self):
        from core.models import Sound

        response = "Prediction Summary:\n"
        for layer in self.layers:
            try:
                sound = Sound.objects.get(pk=layer.sound_id)
                response += f"- {sound.title} by {sound.artist_name} at gain {layer.sound_gain}\n"
            except Sound.DoesNotExist:
                response += f"- Sound ID {layer.sound_id} not found at gain {layer.sound_gain}\n"
        return response


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

    @property
    def avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return get_random_avatar_url(self.pk)

    @property
    def is_anonymous_account(self):
        return bool(self.email) and self.email.endswith("@anon.cosound.ca")


class Listener(DjangoDB.Model):
    user = DjangoDB.OneToOneField(User, on_delete=DjangoDB.CASCADE)
    collection = DjangoDB.ManyToManyField(Sound, blank=True, related_name="saved_by")
    created_at = DjangoDB.DateTimeField(auto_now_add=True)
    updated_at = DjangoDB.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.user)

    def collected(self) -> list[Sound]:
        return list(self.collection.all())


class ListenerPresence(DjangoDB.Model):
    """The most recent NFC visit by one listener at one player."""

    player = DjangoDB.ForeignKey("Player", on_delete=DjangoDB.CASCADE)
    listener = DjangoDB.ForeignKey(Listener, on_delete=DjangoDB.CASCADE)
    visited_at = DjangoDB.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        constraints = [
            DjangoDB.UniqueConstraint(
                fields=["player", "listener"], name="unique_listener_presence"
            )
        ]


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


class Artist(DjangoDB.Model):
    user = DjangoDB.ForeignKey(User, on_delete=DjangoDB.SET_NULL, null=True, blank=True)
    name = DjangoDB.CharField(max_length=255)
    bio = DjangoDB.TextField(blank=True)
    url = DjangoDB.URLField(blank=True)
    avatar = DjangoDB.ImageField(
        upload_to="artist_avatars/", blank=True, null=True, max_length=255
    )
    cover = DjangoDB.ImageField(
        upload_to="artist_covers/", blank=True, null=True, max_length=255
    )
    created_at = DjangoDB.DateTimeField(auto_now_add=True)
    updated_at = DjangoDB.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    def singles(self) -> list["Sound"]:
        """Sounds by this artist that are not grouped into a set."""
        return list(self.sounds.filter(set__isnull=True))


class Set(DjangoDB.Model):
    artist = DjangoDB.ForeignKey(
        Artist, on_delete=DjangoDB.CASCADE, related_name="sets"
    )
    name = DjangoDB.CharField(max_length=255)
    bio = DjangoDB.TextField(blank=True)
    cover = DjangoDB.ImageField(
        upload_to="set_covers/", blank=True, null=True, max_length=255
    )
    created_at = DjangoDB.DateTimeField(auto_now_add=True)
    updated_at = DjangoDB.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Player(DjangoDB.Model):
    program = DjangoDB.OneToOneField(
        "PlayerProgram",
        on_delete=DjangoDB.PROTECT,
        related_name="player",
        blank=True,
    )
    playing: Prediction = SchemaField(default=Prediction)
    sleeping = DjangoDB.BooleanField(default=True)
    activated_at = DjangoDB.DateTimeField(blank=True, null=True)
    manager = DjangoDB.ForeignKey(Manager, on_delete=DjangoDB.CASCADE)
    token = DjangoDB.CharField(max_length=64, unique=True, editable=False)
    name = DjangoDB.CharField(max_length=255)
    photo = DjangoDB.ImageField(
        upload_to="photos/", blank=True, null=True, max_length=255
    )
    bio = DjangoDB.TextField(blank=True, max_length=200)
    location = DjangoDB.CharField(max_length=255, blank=True)
    state_refresh_interval_seconds = DjangoDB.PositiveIntegerField(
        default=settings.PLAYER_STATE_REFRESH_INTERVAL_SECONDS,
        validators=[MinValueValidator(MIN_PLAYER_STATE_REFRESH_SECONDS)],
        verbose_name="fallback state poll interval (seconds)",
        help_text=(
            "How often the physical player checks for missed state changes "
            "(minimum 5). Live updates still arrive immediately."
        ),
    )
    current_exposure = DjangoDB.ForeignKey(
        "PlaybackExposure",
        on_delete=DjangoDB.SET_NULL,
        null=True,
        blank=True,
        related_name="current_for_players",
    )

    class Meta:
        constraints = [
            DjangoDB.CheckConstraint(
                condition=DjangoDB.Q(state_refresh_interval_seconds__gte=5),
                name="player_state_refresh_at_least_5",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            if not update_fields:
                return
        sleeping = not bool(self.playing)
        if self.sleeping != sleeping:
            self.sleeping = sleeping
            if update_fields is not None:
                update_fields.add("sleeping")
        if sleeping and self.activated_at is not None:
            self.activated_at = None
            if update_fields is not None:
                update_fields.add("activated_at")
        if not self.token:
            self.token = secrets.token_hex(32)
            if update_fields is not None:
                update_fields.add("token")
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        kwargs["using"] = using
        if update_fields is not None:
            kwargs["update_fields"] = update_fields
        program_field = self._meta.get_field("program")
        supplied_program = program_field.get_cached_value(self, default=None)
        if self.program_id is not None or supplied_program is not None:
            # Keep Django's normal unsaved-related-object validation when a
            # caller explicitly supplied an unsaved PlayerProgram.
            return super().save(*args, **kwargs)

        # New players retain the public name/bio they previously displayed.
        # A separately authored PlayerProgram keeps the shared Post draft default.
        # Both records must commit together, including when the player fails a
        # uniqueness constraint or the caller is using another database.
        created_program = None
        try:
            with transaction.atomic(using=using):
                composer_id = Manager.objects.using(using).values_list(
                    "user_id", flat=True
                ).get(pk=self.manager_id)
                shared_post = Post.objects.using(using).create(
                    title=self.name,
                    article=self.bio,
                    composer_id=composer_id,
                    publication_date=timezone.now(),
                )
                created_program = PlayerProgram.objects.using(using).create(
                    post=shared_post
                )
                self.program = created_program
                if update_fields is not None:
                    update_fields.add("program")
                return super().save(*args, **kwargs)
        except Exception:
            if created_program is not None:
                # Permit retrying this instance after its creation rolls back.
                self.program = None
            raise

    def library(self) -> List[Sound]:
        return list(self.program.collection.published())

    def update(self, prediction: Prediction) -> None:
        self.playing = prediction
        self.save(update_fields=["playing"])

    def announce(self, prediction: Prediction) -> None:
        print(f"New Prediction for \033[1m{self.name}\033[22m:")
        print(prediction.summary())


class AlgorithmDecision(DjangoDB.Model):
    """One versioned predictor decision, including holds and no-action results.

    Append-only: nothing in the request path reads these rows. They exist so a
    mix that surprised the room can be explained afterwards, which is why a
    hold is recorded as faithfully as a change.
    """

    decision_id = DjangoDB.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    player = DjangoDB.ForeignKey(
        Player,
        on_delete=DjangoDB.CASCADE,
        related_name="algorithm_decisions",
    )
    policy_version = DjangoDB.CharField(max_length=64)
    configuration = DjangoDB.JSONField(default=dict)
    decided_at = DjangoDB.DateTimeField(default=timezone.now, db_index=True)
    previous_layers = DjangoDB.JSONField(default=list)
    selected_layers = DjangoDB.JSONField(default=list)
    active_listener_ids = DjangoDB.JSONField(default=list)
    input_snapshot = DjangoDB.JSONField(default=dict)
    outcome = DjangoDB.CharField(max_length=64)
    selected_score = DjangoDB.FloatField(null=True, blank=True)
    selected_action_probability = DjangoDB.FloatField(default=1.0)
    exploration = DjangoDB.BooleanField(default=False)
    trace = DjangoDB.JSONField(default=dict)

    class Meta:
        ordering = ["decided_at", "decision_id"]

    def __str__(self):
        return f"{self.player_id} {self.outcome} at {self.decided_at:%Y-%m-%d %H:%M}"


class PlaybackExposure(DjangoDB.Model):
    """A server-commanded playback interval.

    Two things depend on it. The predictor reads ``commanded_at`` to know how
    long the current mix has been up, which is what the minimum hold is
    measured against; and a Vote points at the exposure that was live when it
    was cast, so a vote can later be tied to the exact mix it was about rather
    than to whatever is playing by the time anyone looks.

    ``acknowledged_at``, ``transition_seconds`` and ``estimated_audible_at``
    are filled in only by a player confirming it has queued the mix. No such
    call exists here, so they stay null and ``last_change_at`` falls back to
    ``commanded_at``. The fields are kept so that adding the acknowledgement
    later is a pure addition.
    """

    COMMANDED = "commanded"
    PLAYER_ACKNOWLEDGED = "player_acknowledged"
    ENDED = "ended"
    FAILED = "failed"
    STATUS_CHOICES = [
        (COMMANDED, "Commanded"),
        (PLAYER_ACKNOWLEDGED, "Player acknowledged"),
        (ENDED, "Ended"),
        (FAILED, "Failed"),
    ]

    exposure_id = DjangoDB.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    player = DjangoDB.ForeignKey(
        Player,
        on_delete=DjangoDB.CASCADE,
        related_name="playback_exposures",
    )
    opening_decision = DjangoDB.OneToOneField(
        AlgorithmDecision,
        on_delete=DjangoDB.CASCADE,
        related_name="opened_exposure",
    )
    mix_key = DjangoDB.CharField(max_length=255, db_index=True)
    layers = DjangoDB.JSONField(default=list)
    commanded_at = DjangoDB.DateTimeField(default=timezone.now, db_index=True)
    acknowledged_at = DjangoDB.DateTimeField(null=True, blank=True)
    transition_seconds = DjangoDB.FloatField(null=True, blank=True)
    estimated_audible_at = DjangoDB.DateTimeField(null=True, blank=True)
    ended_at = DjangoDB.DateTimeField(null=True, blank=True)
    status = DjangoDB.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=COMMANDED,
    )
    updated_at = DjangoDB.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["commanded_at", "exposure_id"]

    def __str__(self):
        return f"{self.player_id} {self.mix_key} ({self.status})"


def validate_authors(authors):
    """Validate embedded author credits without creating an Author model."""
    if not isinstance(authors, list):
        raise ValidationError("Authors must be a list.")

    validate_url = URLValidator()
    for index, author in enumerate(authors, start=1):
        if not isinstance(author, dict):
            raise ValidationError(f"Author {index} must be an object.")
        unknown = set(author) - {"name", "role", "url"}
        if unknown:
            raise ValidationError(
                f"Author {index} has unsupported fields: {', '.join(sorted(unknown))}."
            )
        for field in ("name", "role"):
            value = author.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"Author {index} requires a {field}.")
        url = author.get("url", "")
        if url:
            if not isinstance(url, str):
                raise ValidationError(f"Author {index} URL must be text.")
            try:
                validate_url(url)
            except ValidationError as error:
                raise ValidationError(f"Author {index} has an invalid URL.") from error


class Post(DjangoDB.Model):
    """Shared writing and discussion, independent of a playback source."""

    announcers_call = DjangoDB.CharField(max_length=100, default="Presenting")
    title = DjangoDB.CharField(max_length=255)
    greeting_style = DjangoDB.CharField(max_length=100, default="Dear Listener")
    font_family = DjangoDB.CharField(
        max_length=100,
        default="dancing-script",
        blank=True,
        help_text="Typography available to selected elements in the post template.",
    )
    article = DjangoDB.TextField(blank=True)
    authors = DjangoDB.JSONField(
        default=list,
        blank=True,
        validators=[validate_authors],
        help_text='A list of objects with "name", "role", and an optional "url".',
    )
    composer = DjangoDB.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=DjangoDB.PROTECT,
        related_name="composed_posts",
    )
    slug = DjangoDB.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    publication_date = DjangoDB.DateTimeField(blank=True, null=True)
    created_at = DjangoDB.DateTimeField(auto_now_add=True)
    updated_at = DjangoDB.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-publication_date", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def font_css_stack(self):
        return article_font_css_stack(self.font_family)


class PlayerProgram(DjangoDB.Model):
    """A player's post, selectable sounds, and playback policy."""

    post = DjangoDB.ForeignKey(
        Post,
        on_delete=DjangoDB.PROTECT,
        related_name="player_programs",
    )
    collection = DjangoDB.ManyToManyField(Sound, blank=True)
    algorithm_refresh_interval_seconds = DjangoDB.PositiveIntegerField(
        default=settings.COSOUND_REFRESH_INTERVAL_SECONDS,
        validators=[MinValueValidator(MIN_ALGORITHM_REFRESH_SECONDS)],
        verbose_name="refresh interval (seconds)",
        help_text="How often the server re-runs this program's algorithm (minimum 5).",
    )
    algorithm_min_layers = DjangoDB.PositiveSmallIntegerField(
        default=settings.COSOUND_MIN_LAYERS,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_ALGORITHM_LAYERS)],
        verbose_name="minimum layers",
        help_text="Minimum number of sounds in a generated mix.",
    )
    algorithm_max_layers = DjangoDB.PositiveSmallIntegerField(
        default=settings.COSOUND_MAX_LAYERS,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_ALGORITHM_LAYERS)],
        verbose_name="maximum layers",
        help_text=(
            "Maximum number of sounds in a generated mix. Larger values make "
            "the initial candidate search grow quickly."
        ),
    )
    algorithm_active_listener_minutes = DjangoDB.PositiveIntegerField(
        default=settings.COSOUND_ACTIVE_LISTENER_MINUTES,
        validators=[MinValueValidator(1)],
        verbose_name="active listener window (minutes)",
        help_text="A listener's visits or votes influence the mix for this long.",
    )
    algorithm_sleep_after_minutes = DjangoDB.PositiveIntegerField(
        default=settings.COSOUND_SLEEP_AFTER_MINUTES,
        validators=[MinValueValidator(1)],
        verbose_name="sleep after (minutes)",
        help_text="Put this program's player to sleep after this much inactivity.",
    )
    algorithm_minimum_hold_seconds = DjangoDB.PositiveIntegerField(
        default=settings.COSOUND_MINIMUM_HOLD_SECONDS,
        verbose_name="minimum hold (seconds)",
        help_text="Keep a selected mix for at least this long before reconsidering it.",
    )
    algorithm_maximum_stay_seconds = DjangoDB.PositiveIntegerField(
        default=settings.COSOUND_MAX_STAY_SECONDS,
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="maximum stay (seconds)",
        help_text="Force eventual rotation after this long. Leave blank for no limit.",
    )
    algorithm_disagreement_penalty = DjangoDB.FloatField(
        default=settings.COSOUND_DISAGREEMENT_PENALTY,
        validators=[MinValueValidator(0.0)],
        verbose_name="disagreement penalty",
        help_text="Higher values favor consensus over mixes that split the room.",
    )
    algorithm_exploration_probability = DjangoDB.FloatField(
        default=settings.COSOUND_EXPLORATION_PROBABILITY,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        verbose_name="exploration probability",
        help_text="Chance of trying another highly ranked mix, from 0 to 1.",
    )
    algorithm_exploration_size = DjangoDB.PositiveIntegerField(
        default=settings.COSOUND_EXPLORATION_SIZE,
        validators=[MinValueValidator(1)],
        verbose_name="exploration pool size",
        help_text="Number of top-ranked candidates that exploration may choose from.",
    )
    baseline = DjangoDB.ForeignKey(
        Sound,
        on_delete=DjangoDB.SET_NULL,
        null=True,
        blank=True,
        related_name="baseline_programs",
        verbose_name="baseline",
        help_text=(
            "Optional fallback when no listener evidence or valid mix exists. "
            "The baseline must also be in this program's sound collection."
        ),
    )
    chime = DjangoDB.FileField(
        upload_to=chime_upload_path,
        blank=True,
        max_length=255,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["wav", "flac", "ogg", "mp3", "aif", "aiff"]
            ),
            validate_chime,
        ],
        verbose_name="vote confirmation chime",
        help_text=(
            "Played by this program's player when a listener vote is received. "
            "Maximum 5 seconds and 5 MB. Supported formats: WAV, FLAC, OGG, "
            "MP3, and AIFF."
        ),
    )
    chime_volume = DjangoDB.FloatField(
        default=settings.COSOUND_CHIME_VOLUME,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        verbose_name="chime volume",
        help_text=(
            "How loud the chime is against the mix it interrupts, from 0 to 1. "
            "The player matches it to the running loudness of whatever it is "
            "already playing, so one setting sounds the same in a sparse mix "
            "and a dense one. 0.25 is level with the soundscape, 1.0 is four "
            "times its level and carries over everything, and 0 silences it."
        ),
    )

    class Meta:
        ordering = ["-post__publication_date", "-post__created_at"]
        constraints = [
            DjangoDB.CheckConstraint(
                condition=DjangoDB.Q(algorithm_refresh_interval_seconds__gte=5),
                name="playerprogram_algorithm_refresh_at_least_5",
            ),
            DjangoDB.CheckConstraint(
                condition=(
                    DjangoDB.Q(algorithm_min_layers__gte=1)
                    & DjangoDB.Q(algorithm_min_layers__lte=MAX_ALGORITHM_LAYERS)
                    & DjangoDB.Q(algorithm_max_layers__gte=1)
                    & DjangoDB.Q(algorithm_max_layers__lte=MAX_ALGORITHM_LAYERS)
                    & DjangoDB.Q(
                        algorithm_min_layers__lte=DjangoDB.F(
                            "algorithm_max_layers"
                        )
                    )
                ),
                name="playerprogram_algorithm_layer_range",
            ),
            DjangoDB.CheckConstraint(
                condition=(
                    DjangoDB.Q(algorithm_active_listener_minutes__gte=1)
                    & DjangoDB.Q(
                        algorithm_sleep_after_minutes__gte=DjangoDB.F(
                            "algorithm_active_listener_minutes"
                        )
                    )
                ),
                name="playerprogram_algorithm_listener_windows",
            ),
            DjangoDB.CheckConstraint(
                condition=(
                    DjangoDB.Q(algorithm_maximum_stay_seconds__isnull=True)
                    | (
                        DjangoDB.Q(algorithm_maximum_stay_seconds__gte=1)
                        & DjangoDB.Q(
                            algorithm_maximum_stay_seconds__gte=DjangoDB.F(
                                "algorithm_minimum_hold_seconds"
                            )
                        )
                    )
                ),
                name="playerprogram_algorithm_stay_after_hold",
            ),
            DjangoDB.CheckConstraint(
                condition=DjangoDB.Q(algorithm_disagreement_penalty__gte=0),
                name="playerprogram_algorithm_nonnegative_penalty",
            ),
            DjangoDB.CheckConstraint(
                condition=(
                    DjangoDB.Q(algorithm_exploration_probability__gte=0)
                    & DjangoDB.Q(algorithm_exploration_probability__lte=1)
                ),
                name="playerprogram_algorithm_probability_range",
            ),
            DjangoDB.CheckConstraint(
                condition=DjangoDB.Q(algorithm_exploration_size__gte=1),
                name="playerprogram_algorithm_exploration_size",
            ),
            DjangoDB.CheckConstraint(
                condition=(
                    DjangoDB.Q(chime_volume__gte=0)
                    & DjangoDB.Q(chime_volume__lte=1)
                ),
                name="playerprogram_chime_volume_range",
            ),
        ]

    def __str__(self):
        return str(self.post)

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.algorithm_min_layers is not None
            and self.algorithm_max_layers is not None
            and self.algorithm_min_layers > self.algorithm_max_layers
        ):
            errors["algorithm_max_layers"] = (
                "Maximum layers cannot be lower than minimum layers."
            )
        maximum_stay = self.algorithm_maximum_stay_seconds
        if (
            maximum_stay is not None
            and self.algorithm_minimum_hold_seconds is not None
            and maximum_stay < self.algorithm_minimum_hold_seconds
        ):
            errors["algorithm_maximum_stay_seconds"] = (
                "Maximum stay cannot be shorter than the minimum hold."
            )
        if (
            self.algorithm_active_listener_minutes is not None
            and self.algorithm_sleep_after_minutes is not None
            and self.algorithm_sleep_after_minutes
            < self.algorithm_active_listener_minutes
        ):
            errors["algorithm_sleep_after_minutes"] = (
                "Sleep time cannot be shorter than the active listener window."
            )
        if (
            self.algorithm_disagreement_penalty is not None
            and not math.isfinite(self.algorithm_disagreement_penalty)
        ):
            errors["algorithm_disagreement_penalty"] = "Enter a finite number."
        if (
            self.algorithm_exploration_probability is not None
            and not math.isfinite(self.algorithm_exploration_probability)
        ):
            errors["algorithm_exploration_probability"] = "Enter a finite number."
        if self.chime_volume is not None and not math.isfinite(self.chime_volume):
            errors["chime_volume"] = "Enter a finite number."
        if self.baseline_id is not None:
            submitted_ids = getattr(self, "_submitted_collection_sound_ids", None)
            if submitted_ids is not None:
                in_collection = self.baseline_id in submitted_ids
            else:
                using = self._state.db or router.db_for_read(
                    type(self),
                    instance=self,
                )
                in_collection = bool(
                    self.pk
                    and type(self)
                    .objects.using(using)
                    .filter(
                        pk=self.pk,
                        collection__pk=self.baseline_id,
                    )
                    .exists()
                )
            if not in_collection:
                errors["baseline"] = (
                    "The baseline must be in this program's sound collection."
                )
        if errors:
            raise ValidationError(errors)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        if "chime" in field_names:
            value = values[field_names.index("chime")]
            instance._loaded_chime_name = value or ""
        return instance

    def refresh_from_db(self, using=None, fields=None, **kwargs):
        if fields is not None:
            fields = tuple(fields)
        result = super().refresh_from_db(using=using, fields=fields, **kwargs)
        if fields is None or "chime" in fields:
            self._loaded_chime_name = self.chime.name if self.chime else ""
        return result

    def save(self, *args, **kwargs):
        """Serialize chime updates and preserve untouched values from stale forms."""
        using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        kwargs["using"] = using
        if self._state.adding or self.pk is None:
            result = super().save(*args, **kwargs)
            self._loaded_chime_name = self.chime.name if self.chime else ""
            return result

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = frozenset(update_fields)
            kwargs["update_fields"] = update_fields
        if update_fields is not None and "chime" not in update_fields:
            return super().save(*args, **kwargs)

        # The chime signal reads the previous storage key before saving and
        # removes it after commit. Keep that read and write behind one row lock;
        # otherwise two concurrent replacements can both observe the same old
        # key and leave whichever new upload loses the database race orphaned.
        with transaction.atomic(using=using):
            locked = (
                type(self)
                .objects.using(using)
                .select_for_update()
                .only("pk", "chime")
                .get(pk=self.pk)
            )
            database_name = locked.chime.name if locked.chime else ""
            current_name = self.chime.name if self.chime else ""
            loaded_name = getattr(self, "_loaded_chime_name", None)
            newly_uploaded = bool(
                self.chime
                and not getattr(self.chime, "_committed", True)
            )
            if (
                loaded_name is not None
                and not newly_uploaded
                and current_name == loaded_name
                and database_name != current_name
            ):
                # The caller changed another field on an instance loaded before
                # a concurrent chime update. Do not restore its stale file key.
                self.chime = database_name

            result = super().save(*args, **kwargs)
            self._loaded_chime_name = self.chime.name if self.chime else ""
            return result

    @property
    def chime_version(self):
        """Stable cache identity that changes with every managed upload."""
        if not self.chime:
            return ""
        return hashlib.sha256(self.chime.name.encode("utf-8")).hexdigest()

    def get_absolute_url(self):
        try:
            player = self.player
        except Player.DoesNotExist:
            return reverse("vote:vote", urlconf="config.urls")
        return reverse(
            "vote:vote", urlconf="config.urls", query={"player": player.token}
        )


class Comment(DjangoDB.Model):
    """A listener's single, permanent response to a post."""

    post = DjangoDB.ForeignKey(
        Post,
        on_delete=DjangoDB.CASCADE,
        related_name="comments",
    )
    user = DjangoDB.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=DjangoDB.CASCADE,
        related_name="comments",
    )
    body = DjangoDB.TextField(max_length=2000)
    created_at = DjangoDB.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            DjangoDB.UniqueConstraint(
                fields=["post", "user"],
                name="unique_comment_per_user_post",
            )
        ]

    def __str__(self):
        return f"{self.user} on {self.post}"
