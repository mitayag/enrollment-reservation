from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.section import Section
from app.models.student import Student
from app.security import manila_date_range_to_utc


def query_students_report(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    year_level: int | None,
    section_id: int | None,
) -> list[Student]:
    stmt = (
        select(Student)
        .options(joinedload(Student.section))
        .where(Student.deleted_at.is_(None))
        .order_by(Student.created_at.desc())
    )
    start_utc, end_utc = manila_date_range_to_utc(date_from, date_to)
    if start_utc is not None:
        stmt = stmt.where(Student.created_at >= start_utc)
    if end_utc is not None:
        stmt = stmt.where(Student.created_at < end_utc)
    if year_level is not None:
        stmt = stmt.join(Section).where(Section.year_level == year_level)
    if section_id is not None:
        stmt = stmt.where(Student.section_id == section_id)
    return list(db.scalars(stmt).unique())


CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: str) -> str:
    """Neutralize spreadsheet formula injection in CSV exports."""
    if value and value.startswith(CSV_INJECTION_PREFIXES):
        return "'" + value
    return value


def student_report_rows(students: list[Student]) -> list[list[str]]:
    rows = []
    for s in students:
        rows.append(
            [
                str(s.id),
                s.last_name,
                s.first_name,
                s.middle_initial or "",
                s.telephone or "",
                s.email or "",
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
    "Section",
    "Year Level",
    "Encoded At (ISO-8601 UTC)",
]
