from datetime import datetime, timezone, timedelta
from typing import Iterable, List

from django.db import models as db_models

from core.models import Cosound, Player, Listener


class Vote(db_models.Model):  # Database Class

    UPVOTE = 1
    DOWNVOTE = 0

    # How well we can trust that this vote is about the mix we think it is.
    # Only the first two are reachable today: the remaining two require the
    # player to confirm it has queued a mix, and nothing asks it to.
    UNATTRIBUTED = "unattributed"
    SERVER_CURRENT = "server_current"
    TRANSITION_UNCERTAIN = "transition_uncertain"
    PLAYER_ACKNOWLEDGED = "player_acknowledged"
    ATTRIBUTION_CHOICES = [
        (UNATTRIBUTED, "Unattributed"),
        (SERVER_CURRENT, "Server current exposure"),
        (TRANSITION_UNCERTAIN, "Player transition uncertain"),
        (PLAYER_ACKNOWLEDGED, "Player acknowledged exposure"),
    ]

    voter = db_models.ForeignKey(
        Listener,
        on_delete=db_models.CASCADE,
    )
    player = db_models.ForeignKey(
        Player,
        on_delete=db_models.CASCADE,
    )
    cosound = db_models.ForeignKey(
        Cosound,
        on_delete=db_models.CASCADE,
    )
    pleasant = db_models.IntegerField()
    section = db_models.CharField(max_length=255, blank=True, default="")
    exposure = db_models.ForeignKey(
        "core.PlaybackExposure",
        on_delete=db_models.SET_NULL,
        null=True,
        blank=True,
        related_name="votes",
    )
    attribution_quality = db_models.CharField(
        max_length=32,
        choices=ATTRIBUTION_CHOICES,
        default=UNATTRIBUTED,
    )
    created_at = db_models.DateTimeField(auto_now_add=True)
    updated_at = db_models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.voter} voted {self.pleasant} for {self.player}"

    @classmethod
    def recent(cls, player: Player, minutes: int = 30) -> List["Vote"]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return list(cls.objects.filter(player=player, created_at__gte=cutoff))

    @staticmethod
    def get_listeners(votes: Iterable["Vote"]) -> List[Listener]:
        seen: dict[int, Listener] = {}
        for vote in votes:
            if vote.voter.pk not in seen:
                seen[vote.voter.pk] = vote.voter
        return list(seen.values())
