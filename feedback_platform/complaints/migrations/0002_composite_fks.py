from django.db import migrations


SQL_ADD = """
ALTER TABLE complaint
    ADD CONSTRAINT fk_complaint_feedback_branch
    FOREIGN KEY (feedback_id, branch_id)
    REFERENCES feedback (id, branch_id);

ALTER TABLE complaint
    ADD CONSTRAINT fk_complaint_branch_org
    FOREIGN KEY (branch_id, organization_id)
    REFERENCES branch (id, organization_id);
"""

SQL_DROP = """
ALTER TABLE complaint DROP CONSTRAINT fk_complaint_feedback_branch;
ALTER TABLE complaint DROP CONSTRAINT fk_complaint_branch_org;
"""


def add_composite_fks(apps, schema_editor):
    """
    Postgres-only. Guarantees at the database level (Phase 2 §D.1):
      - Complaint.branch_id always matches the branch of its parent
        Feedback (via the fk_complaint_feedback_branch constraint,
        referencing the uq_feedback_id_branch unique constraint).
      - Complaint.organization_id always matches Complaint.branch's
        real organization (via fk_complaint_branch_org, referencing
        uq_branch_id_org).

    No-op on SQLite — see feedback/migrations/0002 for the same note.
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
        ("complaints", "0001_initial"),
        ("feedback", "0002_composite_fk_branch_org"),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_composite_fks, remove_composite_fks),
    ]
