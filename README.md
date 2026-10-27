# Enrollment Reservation Management System

Faculty-facing student registration application: FastAPI + Jinja2 + Bootstrap 5 + PostgreSQL.

Phase 1 (foundation): authentication, section management, student management, reporting, dashboard — with CSRF protection, role-based authorization, soft deletes, and UTC storage / Asia-Manila display.

## Stack

- Python 3.12 (image), FastAPI, Jinja2 server-rendered templates, Bootstrap 5 (vendored in `app/static/vendor`, no CDN)
- PostgreSQL 16, SQLAlchemy 2.x, Alembic
- Docker Compose (app + database), pytest

## Project layout

```
app/main.py          Application factory, CSRF middleware, exception handlers
app/config.py        Settings from environment variables
app/database.py      Engine, session factory, declarative base
app/models/          User, Section, Student
app/routers/         auth, dashboard, sections, students, reports, admin
app/services/        Business logic (auth, sections, students, reports)
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

## Security model

- Sessions: signed, HttpOnly, SameSite=Lax cookies (Starlette `SessionMiddleware`); `COOKIE_SECURE=true` behind HTTPS.
- Passwords: bcrypt hashing; minimum 12 characters enforced at creation.
- CSRF: session token verified on every POST/PUT/PATCH/DELETE (`_csrf` form field or `X-CSRF-Token` header); enforced by a body-replaying ASGI middleware.
- Authorization: faculty may view all student records but edit/soft-delete only records they created; administrators may manage all records. Only administrators manage sections and user accounts.
- Soft delete: students carry `deleted_at`; rows are never removed, preserving historical links.
- Section uniqueness: partial unique index on active section names; deactivated sections keep student links and may free a name for reuse.
- Year level: derived from the assigned section; validated on the server.
- Reporting: timestamps stored in UTC, filtered/displayed in Asia/Manila; CSV export neutralizes spreadsheet formula injection.
- Queries: parameterized via SQLAlchemy ORM; logs record method/path/status only — never student personal data.
- Secrets: supplied via environment (`.env`, not committed); no hard-coded credentials anywhere.

## Operations notes (Ubuntu VM / Proxmox, later phase)

- Same `docker compose` commands as above; put `.env` on the VM with a real `SECRET_KEY` and strong database password.
- Terminate TLS in front of the app (e.g., Caddy/nginx) and set `COOKIE_SECURE=true`.
- Back up the `pgdata` volume (e.g., `docker compose exec db pg_dump -U enroll enrolldb`).
