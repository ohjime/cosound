from django.db import migrations, models


class Migration(migrations.Migration):
    """Add Sound.published.

    Every sound that exists today was put there by staff, so they all start
    published. The column's default then drops to False, which is what an
    artist's upload gets: nothing new reaches listeners until it is reviewed.
    """

    dependencies = [
        ("core", "0013_listenerpresence"),
    ]

    operations = [
        migrations.AddField(
            model_name="sound",
            name="published",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="sound",
            name="published",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Reviewed and cleared for everyone. Unpublished sounds are "
                    "heard only by the artist who uploaded them."
                ),
            ),
        ),
    ]
