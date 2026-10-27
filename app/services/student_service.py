from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.section import Section
from app.models.student import Student
from app.models.user import User
from app.security import utc_now

PAGE_SIZE = 25


def list_students(
    db: Session,
    *,
    q: str | None = None,
    section_id: int | None = None,
    year_level: int | None = None,
    include_deleted: bool = False,
    page: int = 1,
) -> tuple[list[Student], int]:
    stmt = select(Student).options(joinedload(Student.section), joinedload(Student.creator))
    if not include_deleted:
        stmt = stmt.where(Student.deleted_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Student.first_name.ilike(like),
                Student.last_name.ilike(like),
                Student.middle_initial.ilike(like),
            )
        )
    if section_id is not None:
        stmt = stmt.where(Student.section_id == section_id)
    if year_level is not None:
        stmt = stmt.join(Section).where(Section.year_level == year_level)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    page = max(page, 1)
    stmt = stmt.order_by(Student.last_name, Student.first_name).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    return list(db.scalars(stmt).unique()), total


def get_student(db: Session, student_id: int) -> Student | None:
    return db.get(Student, student_id)


def validate_student_input(
    db: Session,
    *,
    first_name: str,
    last_name: str,
    middle_initial: str,
    telephone: str,
    email: str,
    section_id: int | None,
    current_section_id: int | None = None,
) -> list[str]:
    errors: list[str] = []
    if not first_name.strip():
        errors.append("First name is required.")
    if not last_name.strip():
        errors.append("Last name is required.")
    if middle_initial.strip() and len(middle_initial.strip()) > 10:
        errors.append("Middle initial must be 10 characters or fewer.")
    if telephone.strip() and len(telephone.strip()) > 50:
        errors.append("Telephone must be 50 characters or fewer.")
    email = email.strip()
    if email and ("@" not in email or len(email) > 255):
        errors.append("A valid email address is required.")

    if section_id is None:
        errors.append("Section is required.")
    else:
        section = db.get(Section, section_id)
        if section is None:
            errors.append("Selected section does not exist.")
        elif not section.is_active and section.id != current_section_id:
            errors.append("Selected section is not active.")
    return errors


def create_student(
    db: Session,
    *,
    first_name: str,
    last_name: str,
    middle_initial: str,
    telephone: str,
    email: str,
    section_id: int,
    created_by: int,
) -> tuple[Student | None, list[str]]:
    errors = validate_student_input(
        db,
        first_name=first_name,
        last_name=last_name,
        middle_initial=middle_initial,
        telephone=telephone,
        email=email,
        section_id=section_id,
    )
    if errors:
        return None, errors
    student = Student(
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        middle_initial=middle_initial.strip() or None,
        telephone=telephone.strip() or None,
        email=email.strip().lower() or None,
        section_id=section_id,
        created_by=created_by,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student, []


def update_student(
    db: Session,
    student: Student,
    *,
    first_name: str,
    last_name: str,
    middle_initial: str,
    telephone: str,
    email: str,
    section_id: int,
) -> tuple[Student | None, list[str]]:
    errors = validate_student_input(
        db,
        first_name=first_name,
        last_name=last_name,
        middle_initial=middle_initial,
        telephone=telephone,
        email=email,
        section_id=section_id,
        current_section_id=student.section_id,
    )
    if errors:
        return None, errors
    student.first_name = first_name.strip()
    student.last_name = last_name.strip()
    student.middle_initial = middle_initial.strip() or None
    student.telephone = telephone.strip() or None
    student.email = email.strip().lower() or None
    student.section_id = section_id
    db.commit()
    db.refresh(student)
    return student, []


def soft_delete_student(db: Session, student: Student) -> None:
    student.deleted_at = utc_now()
    db.commit()


def can_modify(user: User, student: Student) -> bool:
    return user.role.value == "admin" or student.created_by == user.id
