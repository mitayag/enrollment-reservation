"""enforce NOT NULL sections.program_id after administrator assignment

Run this revision only after every existing section has been assigned an
academic program via Sections → Edit. It refuses to proceed while any
section still has program_id NULL, so no data is silently reclassified.

Revision ID: d5e7f1a2b3c4
Revises: a3f2c8d91e04
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op

revision = "d5e7f1a2b3c4"
down_revision = "a3f2c8d91e04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    remaining = (
        bind.execute(
            sa.text("SELECT COUNT(*) FROM sections WHERE program_id IS NULL")
        ).scalar()
        or 0
    )
    if remaining:
        raise RuntimeError(
            f"{remaining} section(s) still have no academic program assigned. "
            "Assign programs via Sections → Edit in the application, then re-run "
            "'alembic upgrade head'."
        )
    if bind.dialect.name == "postgresql":
        op.alter_column("sections", "program_id", nullable=False)
    # SQLite (test databases are created from metadata, not migrations)
    # cannot ALTER COLUMN SET NOT NULL; the NOT NULL guarantee there is
    # provided by application validation.


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column("sections", "program_id", nullable=True)
