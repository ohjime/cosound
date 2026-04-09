from django.db import models


class SoundRating(models.Model):
    user = models.ForeignKey(
        "core.User", on_delete=models.CASCADE, related_name="sound_ratings"
    )
    sound = models.ForeignKey(
        "core.Sound", on_delete=models.CASCADE, related_name="ratings"
    )
    rating = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "sound")]

    def __str__(self):
        return f"{self.user.email} — {self.sound.title}: {self.rating}"
