import logging

from sqlalchemy.orm import Session

from app.models.user import User
from app.security import hash_password, password_policy_errors, verify_password

logger = logging.getLogger("enrollment.security")


def change_own_password(
    db: Session, user: User, *, current_password: str, new_password: str, confirm_password: str
) -> list[str]:
    errors: list[str] = []
    if not verify_password(current_password, user.password_hash):
        errors.append("Current password is incorrect.")
    errors.extend(password_policy_errors(new_password))
    if new_password != confirm_password:
        errors.append("New password and confirmation do not match.")
    if not errors and new_password == current_password:
        errors.append("New password must be different from the current password.")
    if errors:
        return errors
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.commit()
    logger.info("password changed by user_id=%s", user.id)
    return []


def admin_reset_password(
    db: Session, *, actor: User, target: User, new_password: str
) -> list[str]:
    errors: list[str] = []
    if target.id == actor.id:
        errors.append("Use the Change Password page to change your own password.")
    errors.extend(password_policy_errors(new_password))
    if errors:
        return errors
    target.password_hash = hash_password(new_password)
    target.must_change_password = True
    db.commit()
    # Log the action only — never the password or other personal data.
    logger.info(
        "administrator password reset actor_id=%s target_id=%s", actor.id, target.id
    )
    return []


def regenerate_session_after_password_change(request, user: User) -> None:
    """Drop all pre-existing session data and re-authenticate with a fresh cookie."""
    request.session.clear()
    request.session["user_id"] = user.id
