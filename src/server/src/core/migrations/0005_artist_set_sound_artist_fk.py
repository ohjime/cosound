import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0004_alter_sound_flavor'),
    ]

    operations = [
        migrations.CreateModel(
            name='Artist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('bio', models.TextField(blank=True)),
                ('url', models.URLField(blank=True)),
                ('avatar', models.ImageField(blank=True, max_length=255, null=True, upload_to='artist_avatars/')),
                ('cover', models.ImageField(blank=True, max_length=255, null=True, upload_to='artist_covers/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Set',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('bio', models.TextField(blank=True)),
                ('cover', models.ImageField(blank=True, max_length=255, null=True, upload_to='set_covers/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('artist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sets', to='core.artist')),
            ],
        ),
        # Preserve the existing free-text artist data by renaming the column,
        # so the conversion command can backfill the new Artist FK from it.
        migrations.RenameField(
            model_name='sound',
            old_name='artist',
            new_name='artist_legacy',
        ),
        migrations.AlterField(
            model_name='sound',
            name='artist_legacy',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='sound',
            name='artist',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sounds', to='core.artist'),
        ),
        migrations.AddField(
            model_name='sound',
            name='set',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sounds', to='core.set'),
        ),
    ]
