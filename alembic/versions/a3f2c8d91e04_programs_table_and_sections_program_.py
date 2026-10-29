"""programs table, seed catalogue, sections.program_id

Revision ID: a3f2c8d91e04
Revises: 6f065db516b3
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op

revision = "a3f2c8d91e04"
down_revision = "6f065db516b3"
branch_labels = None
depends_on = None

SEED_PROGRAMS = [
    ("BSIT-WD", "BS IT - Web Dev"),
    ("BSIT-NA", "BS IT - Net Administration"),
    ("BSCS", "BS CS"),
    ("BSEMC", "BS EMC"),
    ("BSCYB", "BS Cybersecurity"),
    ("BSCYB-3+2", "BS Cybersecurity 3+2"),
]


def upgrade() -> None:
    op.create_table(
        "programs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_programs_code", "programs", ["code"])

    # Seed the catalogue idempotently (safe if re-applied on restored data).
    bind = op.get_bind()
    for code, name in SEED_PROGRAMS:
        exists = bind.execute(
            sa.text("SELECT id FROM programs WHERE code = :code"), {"code": code}
        ).first()
        if exists is None:
            bind.execute(
                sa.text(
                    "INSERT INTO programs (code, name, is_active) VALUES (:code, :name, TRUE)"
                ),
                {"code": code, "name": name},
            )

    # Existing sections keep program_id NULL until an administrator assigns
    # programs; the follow-up revision enforces NOT NULL afterwards.
    op.add_column(
        "sections",
        sa.Column("program_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_sections_program_id", "sections", "programs", ["program_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_sections_program_id", "sections", ["program_id"])

    # Replace the global active-name uniqueness with per-program uniqueness.
    op.drop_index("uq_sections_active_name", table_name="sections")
    op.create_index(
        "uq_sections_program_name",
        "sections",
        ["program_id", "name"],
        unique=True,
        postgresql_where=sa.text("is_active AND program_id IS NOT NULL"),
        sqlite_where=sa.text("is_active AND program_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_sections_program_name", table_name="sections")
    op.create_index(
        "uq_sections_active_name",
        "sections",
        ["name"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active"),
    )
    op.drop_index("ix_sections_program_id", table_name="sections")
    op.drop_constraint("fk_sections_program_id", "sections", type_="foreignkey")
    op.drop_column("sections", "program_id")
    op.drop_table("programs")
