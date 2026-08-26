import django.db.models.deletion
from django.db import migrations, models


def backfill_organization(apps, schema_editor):
    """
    Populate the new organization column from each row's user for any
    pre-existing UserBranch rows (there shouldn't be any in a fresh
    Phase 3A install, but this makes the migration safe regardless).
    """
    UserBranch = apps.get_model("organizations", "UserBranch")
    for link in UserBranch.objects.all():
        link.organization_id = link.user.organization_id
        link.save(update_fields=["organization_id"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0001_initial"),
        ("accounts", "0003_add_uq_user_id_org"),
    ]

    operations = [
        # 1. Add as nullable so any existing rows aren't rejected outright.
        migrations.AddField(
            model_name="userbranch",
            name="organization",
            field=models.ForeignKey(
                to="organizations.organization",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_branch_links",
                null=True,
            ),
        ),
        # 2. Backfill from user.organization for any pre-existing rows.
        migrations.RunPython(backfill_organization, noop_reverse),
        # 3. Now make it required — every row has a value at this point.
        migrations.AlterField(
            model_name="userbranch",
            name="organization",
            field=models.ForeignKey(
                to="organizations.organization",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_branch_links",
            ),
        ),
    ]
