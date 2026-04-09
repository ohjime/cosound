from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_add_user_avatar"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="PlayerAccount",
            new_name="Manager",
        ),
        migrations.RenameField(
            model_name="manager",
            old_name="manager",
            new_name="user",
        ),
    ]
