from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.program import Program

# Canonical program catalogue, seeded idempotently by migration and `python -m app.seed`.
SEED_PROGRAMS: list[tuple[str, str]] = [
    ("BSIT-WD", "BS IT - Web Dev"),
    ("BSIT-NA", "BS IT - Net Administration"),
    ("BSCS", "BS CS"),
    ("BSEMC", "BS EMC"),
    ("BSCYB", "BS Cybersecurity"),
    ("BSCYB-3+2", "BS Cybersecurity 3+2"),
]


def list_programs(db: Session, *, active_only: bool = False) -> list[Program]:
    stmt = select(Program).order_by(Program.code)
    if active_only:
        stmt = stmt.where(Program.is_active.is_(True))
    return list(db.scalars(stmt))


def get_program(db: Session, program_id: int) -> Program | None:
    return db.get(Program, program_id)


def get_program_by_code(db: Session, code: str) -> Program | None:
    return db.scalar(select(Program).where(Program.code == code))


def seed_programs(db: Session) -> list[Program]:
    """Insert any missing catalogue programs. Safe to run repeatedly."""
    created: list[Program] = []
    for code, name in SEED_PROGRAMS:
        existing = get_program_by_code(db, code)
        if existing is None:
            program = Program(code=code, name=name, is_active=True)
            db.add(program)
            created.append(program)
    if created:
        db.commit()
        for program in created:
            db.refresh(program)
    return created
