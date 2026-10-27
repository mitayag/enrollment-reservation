from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import Role, User
from app.security import hash_password, password_policy_errors, verify_password


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    role: Role = Role.faculty,
) -> tuple[User | None, list[str]]:
    errors: list[str] = []
    email = email.strip().lower()
    if not email or "@" not in email:
        errors.append("A valid email address is required.")
    if not full_name.strip():
        errors.append("Full name is required.")
    errors.extend(password_policy_errors(password))
    if db.scalar(select(User).where(User.email == email)) is not None:
        errors.append("A user with this email already exists.")
    if errors:
        return None, errors
    user = User(
        email=email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, []


def set_user_active(db: Session, user: User, is_active: bool) -> None:
    user.is_active = is_active
    db.commit()
