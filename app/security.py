import hashlib
import hmac
import secrets
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import Role, User

MANILA = ZoneInfo("Asia/Manila")
MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def password_policy_errors(password: str) -> list[str]:
    errors = []
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    return errors


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401)
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=401)
    request.state.user = user
    ensure_csrf_token(request)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role is not Role.admin:
        raise HTTPException(status_code=403)
    return user


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["_csrf_token"] = token
    return token


def csrf_token_from_request(request: Request) -> str | None:
    header = request.headers.get("X-CSRF-Token")
    if header:
        return header
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        form = getattr(request, "_form", None)
        if form is None:
            return None
        return form.get("_csrf")
    return None


def csrf_token_valid(session_token: str | None, supplied: str | None) -> bool:
    if not session_token or not supplied:
        return False
    return hmac.compare_digest(session_token, supplied)


def manila_today_bounds_utc(now_utc: datetime | None = None) -> tuple[datetime, datetime]:
    """UTC [start, end) bounds covering 'today' in Asia/Manila."""
    now_utc = now_utc or datetime.now(timezone.utc)
    manila_now = now_utc.astimezone(MANILA)
    start_local = datetime.combine(manila_now.date(), time.min, tzinfo=MANILA)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def manila_date_range_to_utc(date_from, date_to) -> tuple[datetime | None, datetime | None]:
    """Convert inclusive Manila calendar dates to UTC datetimes."""
    start = None
    end = None
    if date_from is not None:
        start = datetime.combine(date_from, time.min, tzinfo=MANILA).astimezone(timezone.utc)
    if date_to is not None:
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=MANILA).astimezone(
            timezone.utc
        )
    return start, end


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def naive_fingerprint(*parts: str) -> str:
    """Stable non-PII fingerprint for correlating log lines without personal data."""
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]
