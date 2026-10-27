from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.section import Section
from app.models.student import Student


def list_sections(db: Session, *, active_only: bool = False) -> list[Section]:
    stmt = select(Section).order_by(Section.year_level, Section.name)
    if active_only:
        stmt = stmt.where(Section.is_active.is_(True))
    return list(db.scalars(stmt))


def get_section(db: Session, section_id: int) -> Section | None:
    return db.get(Section, section_id)


def create_section(
    db: Session, *, name: str, year_level: int, created_by: int
) -> tuple[Section | None, list[str]]:
    errors = validate_section_input(db, name=name, year_level=year_level)
    if errors:
        return None, errors
    section = Section(name=name.strip(), year_level=year_level, is_active=True, created_by=created_by)
    db.add(section)
    db.commit()
    db.refresh(section)
    return section, []


def update_section(
    db: Session, section: Section, *, name: str, year_level: int
) -> tuple[Section | None, list[str]]:
    errors = validate_section_input(
        db, name=name, year_level=year_level, exclude_section_id=section.id
    )
    if errors:
        return None, errors
    section.name = name.strip()
    section.year_level = year_level
    db.commit()
    db.refresh(section)
    return section, []


def set_section_active(db: Session, section: Section, is_active: bool) -> None:
    if is_active:
        # Reactivating must not collide with another active duplicate name.
        duplicate = db.scalar(
            select(Section).where(
                Section.name == section.name,
                Section.is_active.is_(True),
                Section.id != section.id,
            )
        )
        if duplicate is not None:
            raise ValueError("Another active section already uses this name.")
    section.is_active = is_active
    db.commit()


def validate_section_input(
    db: Session, *, name: str, year_level: int, exclude_section_id: int | None = None
) -> list[str]:
    errors: list[str] = []
    name = name.strip()
    if not name:
        errors.append("Section name is required.")
    elif len(name) > 100:
        errors.append("Section name must be 100 characters or fewer.")
    if year_level < 1 or year_level > 4:
        errors.append("Year level must be between 1 and 4.")
    if name:
        stmt = select(Section).where(Section.name == name, Section.is_active.is_(True))
        if exclude_section_id is not None:
            stmt = stmt.where(Section.id != exclude_section_id)
        if db.scalar(stmt) is not None:
            errors.append("An active section with this name already exists.")
    return errors


def student_count_by_section(db: Session, section_id: int) -> int:
    return (
        db.scalar(
            select(func.count(Student.id)).where(
                Student.section_id == section_id, Student.deleted_at.is_(None)
            )
        )
        or 0
    )
