import django.db.models.deletion
import pgvector.django.vector
from pgvector.django import VectorExtension
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        VectorExtension(),
        migrations.CreateModel(
            name="SoundRating",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rating", models.IntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("sound", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ratings", to="core.sound")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sound_ratings", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "unique_together": {("user", "sound")},
            },
        ),
    ]
