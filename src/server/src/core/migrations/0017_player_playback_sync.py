import uuid

from django.db import migrations, models
from django.utils import timezone


def initialize_playback_timelines(apps, schema_editor):
    Player = apps.get_model("core", "Player")
    alias = schema_editor.connection.alias
    effective_at = timezone.now().timestamp() + 2.0
    for player in Player.objects.using(alias).only("pk").iterator():
        Player.objects.using(alias).filter(pk=player.pk).update(playback_sync={
            "version": 1,
            "revision": str(uuid.uuid4()),
            "epoch": effective_at,
            "effective_at": effective_at,
            "fade_seconds": 8.0,
            "previous_layers": [],
        })


class Migration(migrations.Migration):
    dependencies = [("core", "0016_soundlayer_second_pitch_and_turns")]

    operations = [
        migrations.AddField(
            model_name="player",
            name="playback_sync",
            field=models.JSONField(default=dict, editable=False),
        ),
        migrations.RunPython(initialize_playback_timelines, migrations.RunPython.noop),
    ]
