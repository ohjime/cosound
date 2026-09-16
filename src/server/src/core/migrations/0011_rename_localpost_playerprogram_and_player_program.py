import core.models
import core.validators
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_localpost_chime"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="LocalPost",
            new_name="PlayerProgram",
        ),
        migrations.RenameField(
            model_name="player",
            old_name="post",
            new_name="program",
        ),
        migrations.AlterField(
            model_name="playerprogram",
            name="post",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="player_programs",
                to="core.post",
            ),
        ),
        migrations.AlterField(
            model_name="playerprogram",
            name="baseline",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Optional fallback when no listener evidence or valid mix exists. "
                    "The baseline must also be in this program's sound collection."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="baseline_programs",
                to="core.sound",
                verbose_name="baseline",
            ),
        ),
        migrations.AlterField(
            model_name="playerprogram",
            name="algorithm_refresh_interval_seconds",
            field=models.PositiveIntegerField(
                default=30,
                help_text=(
                    "How often the server re-runs this program's algorithm "
                    "(minimum 5)."
                ),
                validators=[django.core.validators.MinValueValidator(5)],
                verbose_name="refresh interval (seconds)",
            ),
        ),
        migrations.AlterField(
            model_name="playerprogram",
            name="algorithm_sleep_after_minutes",
            field=models.PositiveIntegerField(
                default=180,
                help_text=(
                    "Put this program's player to sleep after this much inactivity."
                ),
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="sleep after (minutes)",
            ),
        ),
        migrations.AlterField(
            model_name="playerprogram",
            name="chime",
            field=models.FileField(
                blank=True,
                help_text=(
                    "Played by this program's player when a listener vote is "
                    "received. Maximum 5 seconds and 5 MB. Supported formats: "
                    "WAV, FLAC, OGG, MP3, and AIFF."
                ),
                max_length=255,
                upload_to=core.models.chime_upload_path,
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["wav", "flac", "ogg", "mp3", "aif", "aiff"]
                    ),
                    core.validators.validate_chime,
                ],
                verbose_name="vote confirmation chime",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="playerprogram",
            name="localpost_algorithm_refresh_at_least_5",
        ),
        migrations.RemoveConstraint(
            model_name="playerprogram",
            name="localpost_algorithm_layer_range",
        ),
        migrations.RemoveConstraint(
            model_name="playerprogram",
            name="localpost_algorithm_listener_windows",
        ),
        migrations.RemoveConstraint(
            model_name="playerprogram",
            name="localpost_algorithm_stay_after_hold",
        ),
        migrations.RemoveConstraint(
            model_name="playerprogram",
            name="localpost_algorithm_nonnegative_penalty",
        ),
        migrations.RemoveConstraint(
            model_name="playerprogram",
            name="localpost_algorithm_probability_range",
        ),
        migrations.RemoveConstraint(
            model_name="playerprogram",
            name="localpost_algorithm_exploration_size",
        ),
        migrations.AddConstraint(
            model_name="playerprogram",
            constraint=models.CheckConstraint(
                condition=models.Q(algorithm_refresh_interval_seconds__gte=5),
                name="playerprogram_algorithm_refresh_at_least_5",
            ),
        ),
        migrations.AddConstraint(
            model_name="playerprogram",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(algorithm_min_layers__gte=1)
                    & models.Q(algorithm_min_layers__lte=5)
                    & models.Q(algorithm_max_layers__gte=1)
                    & models.Q(algorithm_max_layers__lte=5)
                    & models.Q(
                        algorithm_min_layers__lte=models.F("algorithm_max_layers")
                    )
                ),
                name="playerprogram_algorithm_layer_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="playerprogram",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(algorithm_active_listener_minutes__gte=1)
                    & models.Q(
                        algorithm_sleep_after_minutes__gte=models.F(
                            "algorithm_active_listener_minutes"
                        )
                    )
                ),
                name="playerprogram_algorithm_listener_windows",
            ),
        ),
        migrations.AddConstraint(
            model_name="playerprogram",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(algorithm_maximum_stay_seconds__isnull=True)
                    | (
                        models.Q(algorithm_maximum_stay_seconds__gte=1)
                        & models.Q(
                            algorithm_maximum_stay_seconds__gte=models.F(
                                "algorithm_minimum_hold_seconds"
                            )
                        )
                    )
                ),
                name="playerprogram_algorithm_stay_after_hold",
            ),
        ),
        migrations.AddConstraint(
            model_name="playerprogram",
            constraint=models.CheckConstraint(
                condition=models.Q(algorithm_disagreement_penalty__gte=0),
                name="playerprogram_algorithm_nonnegative_penalty",
            ),
        ),
        migrations.AddConstraint(
            model_name="playerprogram",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(algorithm_exploration_probability__gte=0)
                    & models.Q(algorithm_exploration_probability__lte=1)
                ),
                name="playerprogram_algorithm_probability_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="playerprogram",
            constraint=models.CheckConstraint(
                condition=models.Q(algorithm_exploration_size__gte=1),
                name="playerprogram_algorithm_exploration_size",
            ),
        ),
    ]
