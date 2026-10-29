# Enrollment Reservation Management System

Faculty-facing student registration application: FastAPI + Jinja2 + Bootstrap 5 + PostgreSQL.

Phase 1: authentication, section management, student management, reporting, dashboard — with CSRF protection, role-based authorization, soft deletes, and UTC storage / Asia-Manila display.

Phase 2: password management (self-service change + administrator-assisted reset with forced change at next login), student masterlist CSV import with column mapping, validation preview, atomic replacement and batch history, plus faculty student lookup from the masterlist when encoding reservations.

Phase 3: academic programs — a seeded program catalogue, sections belonging to programs (unique names per program), program-aware student registration with cascading section selection, program filtering across the student list and reports, and program-grouped report totals.

## Stack

- Python 3.12 (image), FastAPI, Jinja2 server-rendered templates, Bootstrap 5 (vendored in `app/static/vendor`, no CDN)
- PostgreSQL 16, SQLAlchemy 2.x, Alembic
- Docker Compose (app + database), pytest

## Project layout

```
app/main.py          Application factory, CSRF middleware, exception handlers
app/config.py        Settings from environment variables
app/database.py      Engine, session factory, declarative base
app/models/          User, Program, Section, Student, masterlist tables
app/routers/         auth, dashboard, sections, students, reports, admin, masterlist, account
app/services/        Business logic (auth, programs, sections, students, reports, masterlist)
app/templates/       Jinja2 templates (Bootstrap 5)
app/static/          Vendored Bootstrap assets
app/cli.py           One-time administrator provisioning command
alembic/             Database migrations
tests/               pytest suite
docker/entrypoint.sh Waits for DB, then execs the app command
```

## Quick start (development, macOS)

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env: set SECRET_KEY (python -c "import secrets; print(secrets.token_urlsafe(32))")
# and a strong POSTGRES_PASSWORD.

# 2. Start app + database (bind-mounts source, --reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# 3. Run migrations (explicit, in a one-off container)
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm web alembic upgrade head

# 4. Create the first administrator (one-time, interactive credentials)
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm web python -m app.cli create-admin

# 5. Open the app
open http://127.0.0.1:8000
```

Note: start the stack first (step 2) so the database is up, or run steps 3–4 after `db` is healthy. The web container waits for the database automatically.

## Production-style start (no source bind-mounts)

```bash
cp .env.example .env   # set SECRET_KEY, POSTGRES_PASSWORD, COOKIE_SECURE=true (behind HTTPS)
docker compose up --build -d

# Migrations — run explicitly after every deploy that includes new revisions:
docker compose run --rm web alembic upgrade head

# First-time admin:
docker compose run --rm web python -m app.cli create-admin
```

The production compose file:
- builds only the `production` image target (no source mounts, no dev dependencies)
- runs the app as a non-root user
- keeps PostgreSQL port unpublished (only the compose network)
- persists PostgreSQL data in the named volume `pgdata`
- gates startup on the database healthcheck
- maps the app to `127.0.0.1:8000` on the host

## Administrator provisioning

`python -m app.cli create-admin` is the only way the first admin is created. Credentials come from interactive prompts (password via `getpass`, never echoed) or from `ADMIN_EMAIL` / `ADMIN_FULL_NAME` / `ADMIN_PASSWORD` environment variables. There are no default credentials and the command refuses duplicates and passwords shorter than 12 characters.

## Running tests

```bash
# Local venv (tests use in-memory SQLite; no database container needed)
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q

# Inside Docker (development image)
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm web pytest tests/ -q
```

## Database migrations

- Revisions live in `alembic/versions/`.
- Apply forward: `alembic upgrade head` (inside the container; `DATABASE_URL` must point at the running database).
- The entrypoint does **not** run migrations automatically — they are an explicit deploy step.
- Phase 1: `c116480e0082` (initial schema). Phase 2: `6f065db516b3` (password management + student masterlist). Both are unchanged; existing data is preserved.

### Phase 3 rollout (two-step, protects existing sections)

1. `alembic upgrade a3f2c8d91e04` — creates `programs`, seeds the six catalogue programs
   idempotently (BSIT-WD, BSIT-NA, BSCS, BSEMC, BSCYB, BSCYB-3+2), and adds
   `sections.program_id` as a **nullable** foreign key. Existing sections are intentionally
   left unassigned — no program is ever auto-picked for them.
2. Assign a program to every existing section via **Sections → Edit** (the Sections page
   shows an "Unassigned" badge and a warning banner until none remain).
3. `alembic upgrade head` (i.e., `d5e7f1a2b3c4`) — **refuses to run** while any section is
   still unassigned (nothing is silently reclassified); once all are assigned it enforces
   `program_id NOT NULL` and the per-program uniqueness index is fully authoritative.

Re-seeding programs later is safe: `alembic` never duplicates them, and
`python -m app.seed` inserts only missing codes.

## Security model

- Sessions: signed, HttpOnly, SameSite=Lax cookies (Starlette `SessionMiddleware`); `COOKIE_SECURE=true` behind HTTPS.
- Passwords: bcrypt hashing; minimum 12 characters enforced at creation.
- CSRF: session token verified on every POST/PUT/PATCH/DELETE (`_csrf` form field or `X-CSRF-Token` header); enforced by a body-replaying ASGI middleware.
- Authorization: faculty may view all student records but edit/soft-delete only records they created; administrators may manage all records. Only administrators manage sections and user accounts.
- Soft delete: students carry `deleted_at`; rows are never removed, preserving historical links.
- Section uniqueness: active sections are unique by (program, name); the same section name may exist in different programs. Deactivated sections keep student links and may free a name for reuse within their program.
- Year level: chosen alongside the program on student forms; the server verifies the selected section belongs to both before saving, and both are derived from the section relationship on the record.
- Reporting: timestamps stored in UTC, filtered/displayed in Asia/Manila; CSV export neutralizes spreadsheet formula injection.
- Queries: parameterized via SQLAlchemy ORM; logs record method/path/status only — never student personal data.
- Secrets: supplied via environment (`.env`, not committed); no hard-coded credentials anywhere.

## Phase 2 features

### Password management

- **Change own password** (`/account/password`, "Change Password" in the navbar): verifies the current password against the bcrypt hash, enforces the 12-character minimum, rejects mismatches, and regenerates the session (all pre-existing session data, including the CSRF token, is dropped and a fresh cookie is issued).
- **Administrator-assisted reset** (Users → Reset password): administrators set a temporary password (same policy). The user is forced to change it at next login (`users.must_change_password`); until they do, every page except the change-password form and logout redirects there. Reset actions are logged with actor/target user IDs only — never passwords or personal data. Email-based self-service recovery is intentionally out of scope until an SMTP provider is configured.

### Student masterlist CSV import (administrators only)

The **Masterlist** page uploads a UTF-8 CSV (configurable limit, default 10 MB via `MASTERLIST_MAX_UPLOAD_BYTES`), validates it in a background job with real row-by-row progress, previews the first 20 rows with totals (rows / valid / invalid / duplicates), offers a downloadable validation-error report, and — after the administrator types `REPLACE` — atomically replaces the entire `student_masterlist` table in one transaction guarded by a database lock row (concurrent imports are rejected; failures roll back and preserve the previous masterlist). Import batch history (file name, administrator, timestamp, counts) is kept in `import_batches`. Uploaded content lives only in database staging tables — never in public directories — and CSV student data is never written to application logs.

**CSV header assumptions:** recognized headers (case-insensitive, spaces/dashes treated as underscores) are
`student_number, first_name, last_name, middle_initial, telephone, email`, with common aliases such as
`student id / lrn` (student_number), `given name` (first_name), `surname / family name` (last_name),
`mi / middle name` (middle_initial), `phone / mobile` (telephone), `email address` (email).
Only `first_name` and `last_name` must be present; any other format uses the column-mapping step.
Validation: required name fields, field-length limits, email shape, duplicate `student_number` within the
file (excluded), and potential identity duplicates (same name + contact) flagged for review but imported.
The error-report CSV neutralizes spreadsheet formula injection.

### Faculty student lookup

The Add Student page includes "Search Student Masterlist": partial, case-insensitive search by student
number or name (debounced, limited results with incremental "Load more"). Selecting a result only
populates the form — the faculty member reviews/edits, picks a section via the existing Section module,
and saves, which creates an enrollment reservation in `students` (not a masterlist record). Reservations
store the stable `masterlist_student_number` (and a nullable entry id that is nulled if the masterlist is
replaced). When a student number is present, a second active reservation for the same number is rejected.
Manual entry without any lookup still works exactly as in Phase 1.

## Phase 3 features — academic programs

### Program catalogue

The `programs` table holds six seeded programs (unique `code`, `name`, `is_active`,
`created_at`): BSIT-WD (BS IT - Web Dev), BSIT-NA (BS IT - Net Administration), BSCS (BS CS),
BSEMC (BS EMC), BSCYB (BS Cybersecurity), and BSCYB-3+2 (BS Cybersecurity 3+2). Seeding is
idempotent — the migration and `python -m app.seed` only insert missing codes, so re-running
either never duplicates rows.

### Section management with programs

Add/Edit Section now requires a **Program** (dropdown of catalogue programs), Year Level, and
Section Name, and displays the Active/Inactive status. Listing shows Program, Year Level,
Section, and Status. Sections are unique within their program — the same name may exist in
different programs. Pre-existing sections without a program show an "Unassigned" badge and a
warning banner; administrators assign each one via Edit (the finalize migration then enforces
`program_id NOT NULL` at the database level, as described in the migration section).

### Program-aware student registration

Add/Edit Student requires Program and Year Level alongside Section. Section choices cascade:
selecting a program narrows the list to that program's sections, and a year level narrows it
further. Server-side validation rejects any program/year/section combination that does not
match the section's own program and year (mismatched combinations return a controlled 400
with the form state preserved). The record stores only `section_id`; program and year are
derived through the section relationship. Legacy sections that still lack a program remain
usable only for the student currently assigned to them — new registrations must use an
assigned section. Masterlist lookup continues to populate the form exactly as before.

### Student list and reports by program

The Students listing gains a Program column and a Program filter that works alongside name
search, year level, and section — independently or combined, blank parameters treated as
"All" (no 422s), and all active filters preserved across pagination. Section choices respond
dynamically to the selected program and year.

Reports accept date-encoded from/to, Program, Year Level, and Section filters (also
blank-safe). Program appears in the on-screen results, the printable view, and the CSV
export. A "Totals by program" option groups the filtered result set by academic program
(including an Unassigned bucket for legacy sections).

## Operations notes (Ubuntu VM / Proxmox, later phase)

- Same `docker compose` commands as above; put `.env` on the VM with a real `SECRET_KEY` and strong database password.
- Terminate TLS in front of the app (e.g., Caddy/nginx) and set `COOKIE_SECURE=true`.
- Back up the `pgdata` volume (e.g., `docker compose exec db pg_dump -U enroll enrolldb`).
