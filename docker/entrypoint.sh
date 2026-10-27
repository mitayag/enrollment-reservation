#!/bin/sh
set -e

# Wait for the database to accept connections, then exec the given command.
# Migrations are run explicitly (see README), not automatically here.
if [ -n "$DATABASE_URL" ]; then
  python - <<'PY'
import os, sys, time
import sqlalchemy as sa

url = os.environ["DATABASE_URL"]
engine = sa.create_engine(url, pool_pre_ping=True)
for attempt in range(30):
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        sys.exit(0)
    except Exception:
        time.sleep(1)
print("database did not become ready in time", file=sys.stderr)
sys.exit(1)
PY
fi

exec "$@"
