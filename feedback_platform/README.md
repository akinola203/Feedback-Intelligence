# Supermarket Feedback Platform — Phase 3A: Foundation & Database

This is the Django project for the Supermarket Feedback Platform, implementing
the models and constraints from the approved Phase 2 architecture (with
corrections #1–#6 applied). **This is Phase 3A only** — models, migrations,
and category seed data. No authentication, no API endpoints, no QR flow yet.

---

## What's in this phase

11 models across 5 Django apps, matching the Phase 2 groupings:

| App | Models |
|---|---|
| `organizations` | Organization, Branch, UserBranch |
| `accounts` | User (org member), PlatformAdmin |
| `feedback` | Category, QRCode, Feedback |
| `complaints` | Complaint, ComplaintNote |
| `audit` | AuditLog |
| `core` | (shared abstract base model only — no table of its own) |

Key architectural pieces implemented in this phase:

- **UUID primary keys** everywhere (Phase 2 correction #4).
- **Composite foreign keys** enforcing that `Feedback.organization_id` /
  `Complaint.organization_id` / `Complaint.branch_id` can never drift out of
  sync with their real parent records — enforced by PostgreSQL itself, not
  application code (Phase 2 §D.1). See
  `feedback/migrations/0002_composite_fk_branch_org.py` and
  `complaints/migrations/0002_composite_fks.py`.
- **Category as platform-defined for MVP**, with a partial-unique-index fix
  so two global categories can't share a name — the bug a plain composite
  unique constraint would have missed (Phase 2 correction #2). See
  `feedback/models.py::Category.Meta.constraints`.
- **Org-scoped email uniqueness** on `User` (not global), preparing for the
  slug-based login decided in correction #3 — actual login views are Phase 3B.
- **Dual-actor AuditLog** (`actor_user` / `actor_platform_admin`, mutually
  exclusive via a CHECK constraint) so both org and platform actions are
  auditable in one table (Phase 2 correction #5).
- **Passwords hashed via Django's own hashers** (`set_password`/
  `check_password` using `django.contrib.auth.hashers`) — no custom hashing,
  per the Phase 2 instruction. Full login/session/token wiring is Phase 3B.
- **UserBranch cannot cross organizations at the database level.** A denormalized
  `organization` field on `UserBranch`, pinned by composite FKs to both
  `User(id, organization)` and `Branch(id, organization)`, means a User from
  Organization A can never be linked to a Branch in Organization B — enforced
  by PostgreSQL itself. (This was a gap identified in architecture review after
  the initial Phase 3A pass — see "Post-review fix" below.)

## What's deliberately NOT in this phase

Per the Phase 3 plan: no authentication views, no API endpoints, no QR
scan flow, no dashboard, no email notifications, no NLP sentiment,
no automatic complaint creation, no multi-org user membership, no
PostgreSQL RLS, no org-specific category management.

---

## Verification already done

Before handing this to you, I ran (not just wrote) the following, against
**both SQLite and a real local PostgreSQL instance**, on Django 5.2.17 LTS:

- `manage.py check` — no issues.
- `manage.py migrate` — all 8 migrations apply cleanly, including the two
  manual composite-FK migrations, and reverse cleanly.
- `manage.py test` — **23/23 tests pass**, covering: org-scoped uniqueness
  (branch names, user emails), password hashing, QR token uniqueness and
  the one-active-token-per-branch constraint, sentiment derivation from
  rating, the Feedback→Complaint 1-to-0/1 relationship, and the AuditLog
  single-actor constraint.
- **A direct attack on the tenant-isolation guarantee**: created a real
  Feedback row, then tried to force its `organization_id` to a different
  organization via raw SQL (bypassing Django/the application layer
  entirely) while leaving `branch_id` pointed at the original branch.
  **PostgreSQL rejected it**, citing the `fk_feedback_branch_org`
  composite foreign key. This is correction/requirement D.1 verified for
  real, not just asserted.
- Same raw-SQL attack against the global-category uniqueness fix
  (correction #2): tried to insert a second `organization_id = NULL,
  name = 'Staff'` row directly — rejected by `uq_category_global_name`.

---

## Windows setup — exact commands

### 1. Install PostgreSQL (if not already installed)

Download and run the installer from https://www.postgresql.org/download/windows/
Remember the password you set for the `postgres` user during setup.

### 2. Create the database

Open **SQL Shell (psql)** from the Start menu (or use pgAdmin), then:

```sql
CREATE DATABASE feedback_platform;
```

### 3. Get the project files and set up a virtual environment

In PowerShell, from the folder where you unzipped the project:

```powershell
cd feedback_platform
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Configure environment variables

```powershell
copy .env.example .env
```

Then open `.env` in a text editor and set `DB_PASSWORD` to the Postgres
password you chose in step 1 (and `DJANGO_SECRET_KEY` to any long random
string — it doesn't need to be memorable).

### 5. Run migrations

```powershell
python manage.py migrate
```

You should see all 8 migrations apply successfully, ending with
`complaints.0002_composite_fks... OK`.

### 6. Seed the default categories

```powershell
python manage.py seed_categories
```

Should report `9 category(ies) created, 0 already existed.`

### 7. Run the tests

```powershell
python manage.py test
```

Should report `Ran 23 tests ... OK`.

### 8. (Optional) Create a superuser to browse the data in Django admin

```powershell
python manage.py createsuperuser
```

Follow the prompts (this creates a Django built-in admin account, separate
from the `PlatformAdmin`/`User` models — it's just for you to inspect data
in `/admin/` during development). Then:

```powershell
python manage.py runserver
```

Visit `http://127.0.0.1:8000/admin/` and log in — you should see
Organization, Branch, User, Category (with 9 seeded rows), and all other
models listed.

---

## Files created in this phase

```
feedback_platform/
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md                              (this file)
├── config/
│   ├── settings.py                        (apps, DB config from .env, password hashers)
│   ├── urls.py
│   └── ...
├── core/
│   └── models.py                          (shared UUID base model)
├── organizations/
│   ├── models.py                          (Organization, Branch, UserBranch)
│   ├── admin.py
│   ├── tests.py                           (8 tests)
│   └── migrations/0001_initial.py
├── accounts/
│   ├── models.py                          (User, PlatformAdmin)
│   ├── admin.py
│   └── migrations/0001_initial.py, 0002_initial.py
├── feedback/
│   ├── models.py                          (Category, QRCode, Feedback)
│   ├── admin.py
│   ├── tests.py                           (9 tests)
│   ├── management/commands/seed_categories.py
│   └── migrations/0001_initial.py, 0002_composite_fk_branch_org.py
├── complaints/
│   ├── models.py                          (Complaint, ComplaintNote)
│   ├── admin.py
│   ├── tests.py                           (3 tests)
│   └── migrations/0001_initial.py, 0002_composite_fks.py
└── audit/
    ├── models.py                          (AuditLog)
    ├── admin.py
    ├── tests.py                           (4 tests)
    └── migrations/0001_initial.py
```

---

## Post-review fix: UserBranch tenant leak

ChatGPT's review of the Phase 3A zip identified that `UserBranch` allowed
linking a User from Organization A to a Branch in Organization B at the
database level — a real gap, since branch membership is what scopes
Manager/Staff access (Phase 2 §6).

**Fix applied**, scoped to exactly this issue, no other architectural changes:

- Added `UserBranch.organization` (denormalized from `user.organization`,
  auto-derived server-side in `save()`, same D.1 pattern as Feedback/Complaint).
- Added a supporting `(id, organization)` unique constraint on `User`
  (`accounts/migrations/0003_add_uq_user_id_org.py`) — needed as the target
  for a composite FK, the same way `Branch` already had one.
- Added two composite FKs in a new migration
  (`organizations/migrations/0003_userbranch_composite_fks.py`):
  - `fk_userbranch_user_org`: `(user_id, organization_id) → app_user(id, organization_id)`
  - `fk_userbranch_branch_org`: `(branch_id, organization_id) → branch(id, organization_id)`

  Together these pin both the user and the branch in a `UserBranch` row to
  the *same* organization column — PostgreSQL rejects any row where they
  don't match, independent of application code.
- Added two tests in `organizations/tests.py`:
  - `test_cross_organization_userbranch_link_rejected_at_db_level` — attempts
    the cross-org link via the Django ORM, bypassing the model's normal
    derivation logic on purpose.
  - `test_cross_organization_link_also_rejected_via_raw_sql` — attempts the
    same thing via raw SQL, bypassing Django entirely. Both are Postgres-only
    (they self-skip on SQLite, where the composite FK is a no-op by design —
    see the migration file for why).

**Verified against real PostgreSQL:** all 26 tests pass with **0 skipped**
(confirming both new tests actually executed and passed, not skipped past),
and `\d user_branch` in psql confirms both composite FK constraints exist on
the live table.

---

## Files changed in this fix

```
accounts/
├── models.py                                    (added uq_user_id_org constraint)
└── migrations/0003_add_uq_user_id_org.py         (new)

organizations/
├── models.py                                     (UserBranch: added organization field + save())
├── tests.py                                       (added 2 cross-org tests)
├── migrations/0002_userbranch_organization.py    (new — adds + backfills the column)
└── migrations/0003_userbranch_composite_fks.py   (new — the actual DB-level fix)
```

No files in `feedback`, `complaints`, `audit`, or `core` were touched — this
fix is scoped exactly to the reported issue.

---

## Next step

Per the Phase 3 plan: **stop here for review.** Do not proceed to Phase 3B
(Authentication & Tenant Isolation) until you and ChatGPT have reviewed this fix.
