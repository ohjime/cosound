from django.db import models as DjangoDB

from core.models import User, Cosound


class SoundMix(DjangoDB.Model):
    creator = DjangoDB.ForeignKey(User, on_delete=DjangoDB.CASCADE)
    cosound = DjangoDB.ForeignKey(Cosound, on_delete=DjangoDB.CASCADE)
    title = DjangoDB.CharField(max_length=255, blank=True, default="")
    created_at = DjangoDB.DateTimeField(auto_now_add=True)
    updated_at = DjangoDB.DateTimeField(auto_now=True)
