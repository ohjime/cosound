from django.db import models as db_models
from django_pydantic_field import SchemaField

from core.models import Cosound, Player, Listener


class Vote(db_models.Model):  # Database Class

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
    value = db_models.IntegerField()
    created_at = db_models.DateTimeField(auto_now_add=True)
    updated_at = db_models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.voter} voted {self.value} for {self.player}"
