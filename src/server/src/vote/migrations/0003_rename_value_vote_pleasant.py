from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("vote", "0002_vote_attribution_quality_vote_exposure")]

    operations = [migrations.RenameField("vote", "value", "pleasant")]
