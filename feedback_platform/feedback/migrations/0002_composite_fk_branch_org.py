from django.db import migrations


SQL_ADD = """
ALTER TABLE feedback
    ADD CONSTRAINT fk_feedback_branch_org
    FOREIGN KEY (branch_id, organization_id)
    REFERENCES branch (id, organization_id);
"""

SQL_DROP = """
ALTER TABLE feedback DROP CONSTRAINT fk_feedback_branch_org;
"""


def add_composite_fk(apps, schema_editor):
    """
    Postgres-only: enforces that Feedback.organization_id can never drift
    from Feedback.branch.organization_id at the database level, not just
    in application code (Phase 2 §D.1 — the "database, not developer
    discipline" guarantee).

    No-op on SQLite so `manage.py migrate` still works for local model
    checks without a Postgres server; the approved architecture assumes
    Postgres for any real environment, per Phase 2/3.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(SQL_ADD)


def remove_composite_fk(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(SQL_DROP)


class Migration(migrations.Migration):

    dependencies = [
        ("feedback", "0001_initial"),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_composite_fk, remove_composite_fk),
    ]
