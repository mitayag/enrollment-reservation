from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.program import Program
from app.models.section import Section
from app.models.student import Student
from app.security import manila_date_range_to_utc


def _report_stmt(
    *,
    date_from: date | None,
    date_to: date | None,
    year_level: int | None,
    section_id: int | None,
    program_id: int | None,
):
    stmt = (
        select(Student)
        .options(joinedload(Student.section).joinedload(Section.program))
        .where(Student.deleted_at.is_(None))
        .order_by(Student.created_at.desc())
    )
    start_utc, end_utc = manila_date_range_to_utc(date_from, date_to)
    if start_utc is not None:
        stmt = stmt.where(Student.created_at >= start_utc)
    if end_utc is not None:
        stmt = stmt.where(Student.created_at < end_utc)
    if year_level is not None or program_id is not None:
        stmt = stmt.join(Section)
    if year_level is not None:
        stmt = stmt.where(Section.year_level == year_level)
    if program_id is not None:
        stmt = stmt.where(Section.program_id == program_id)
    if section_id is not None:
        stmt = stmt.where(Student.section_id == section_id)
    return stmt


def query_students_report(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    year_level: int | None,
    section_id: int | None,
    program_id: int | None = None,
) -> list[Student]:
    stmt = _report_stmt(
        date_from=date_from,
        date_to=date_to,
        year_level=year_level,
        section_id=section_id,
        program_id=program_id,
    )
    return list(db.scalars(stmt).unique())


def count_by_program(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    year_level: int | None,
    section_id: int | None,
    program_id: int | None = None,
) -> list[tuple[str, str, int]]:
    """Totals for the filtered set, grouped by academic program.

    Returns (code, name, count) tuples; sections without an assigned
    program are grouped under "Unassigned".
    """
    stmt = (
        select(
            Program.code,
            Program.name,
            func.count(Student.id).label("total"),
        )
        .select_from(Student)
        .join(Section, Student.section_id == Section.id)
        .outerjoin(Program, Section.program_id == Program.id)
        .where(Student.deleted_at.is_(None))
        .group_by(Program.code, Program.name)
        .order_by(Program.code)
    )
    start_utc, end_utc = manila_date_range_to_utc(date_from, date_to)
    if start_utc is not None:
        stmt = stmt.where(Student.created_at >= start_utc)
    if end_utc is not None:
        stmt = stmt.where(Student.created_at < end_utc)
    if year_level is not None:
        stmt = stmt.where(Section.year_level == year_level)
    if program_id is not None:
        stmt = stmt.where(Section.program_id == program_id)
    if section_id is not None:
        stmt = stmt.where(Student.section_id == section_id)
    return [
        (code or "—", name or "Unassigned (legacy sections)", count)
        for code, name, count in db.execute(stmt).all()
    ]


CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: str) -> str:
    """Neutralize spreadsheet formula injection in CSV exports."""
    if value and value.startswith(CSV_INJECTION_PREFIXES):
        return "'" + value
    return value


def student_report_rows(students: list[Student]) -> list[list[str]]:
    rows = []
    for s in students:
        program = s.section.program if s.section else None
        rows.append(
            [
                str(s.id),
                s.last_name,
                s.first_name,
                s.middle_initial or "",
                s.telephone or "",
                s.email or "",
                program.code if program else "",
                s.section.name if s.section else "",
                str(s.section.year_level) if s.section else "",
                s.created_at.isoformat() if s.created_at else "",
            ]
        )
    return [[sanitize_csv_cell(cell) for cell in row] for row in rows]


CSV_HEADER = [
    "ID",
    "Last Name",
    "First Name",
    "Middle Initial",
    "Telephone",
    "Email",
    "Program",
    "Section",
    "Year Level",
    "Encoded At (ISO-8601 UTC)",
]
