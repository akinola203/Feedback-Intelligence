from django.db import migrations


SQL_ADD = """
ALTER TABLE user_branch
    ADD CONSTRAINT fk_userbranch_user_org
    FOREIGN KEY (user_id, organization_id)
    REFERENCES app_user (id, organization_id);

ALTER TABLE user_branch
    ADD CONSTRAINT fk_userbranch_branch_org
    FOREIGN KEY (branch_id, organization_id)
    REFERENCES branch (id, organization_id);
"""

SQL_DROP = """
ALTER TABLE user_branch DROP CONSTRAINT fk_userbranch_user_org;
ALTER TABLE user_branch DROP CONSTRAINT fk_userbranch_branch_org;
"""


def add_composite_fks(apps, schema_editor):
    """
    Postgres-only. This is the fix for the reported gap: without these,
    UserBranch allowed linking a User from Organization A to a Branch in
    Organization B at the database level, silently defeating branch-scoped
    access control for Manager/Staff (Phase 2 §6).

    - fk_userbranch_user_org: forces UserBranch.organization_id to match
      the linked User's real organization (references uq_user_id_org).
    - fk_userbranch_branch_org: forces UserBranch.organization_id to match
      the linked Branch's real organization (references uq_branch_id_org,
      already added in the Feedback/Complaint composite-FK work).

    Together, both the user and the branch in a UserBranch row are pinned
    to the SAME organization column — a cross-org link is rejected by
    Postgres itself, not just application code. No-op on SQLite, same as
    the other composite-FK migrations.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(SQL_ADD)


def remove_composite_fks(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(SQL_DROP)


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0002_userbranch_organization"),
        ("accounts", "0003_add_uq_user_id_org"),
        # Needs uq_branch_id_org, added alongside the Feedback composite FK.
        ("feedback", "0002_composite_fk_branch_org"),
    ]

    operations = [
        migrations.RunPython(add_composite_fks, remove_composite_fks),
    ]
