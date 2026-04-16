from django.db import models


class Home(models.Model):
    user = models.ForeignKey(
        "core.User", on_delete=models.CASCADE, related_name="homees"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Home #{self.pk} by {self.user.email}"


class HomeLayer(models.Model):
    home = models.ForeignKey(Home, on_delete=models.CASCADE, related_name="layers")
    sound = models.ForeignKey(
        "core.Sound", on_delete=models.CASCADE, related_name="home_layers"
    )
    user = models.ForeignKey(
        "core.User", on_delete=models.CASCADE, related_name="home_layers"
    )
    gain = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sound.title} @ {self.gain}"
