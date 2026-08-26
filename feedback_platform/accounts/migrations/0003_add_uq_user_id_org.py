from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                fields=["id", "organization"], name="uq_user_id_org"
            ),
        ),
    ]
