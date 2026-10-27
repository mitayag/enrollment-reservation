from datetime import timezone
from pathlib import Path

from starlette.requests import Request
from starlette.templating import Jinja2Templates

from app.security import MANILA, ensure_csrf_token


def _to_manila(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        # SQLite returns naive datetimes; values are always stored in UTC.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(MANILA)


templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
templates.env.filters["manila_time"] = lambda dt: (
    _to_manila(dt).strftime("%Y-%m-%d %H:%M") if dt else ""
)
templates.env.filters["manila_date"] = lambda dt: (
    _to_manila(dt).strftime("%Y-%m-%d") if dt else ""
)


def render(request: Request, name: str, context: dict | None = None, status_code: int = 200):
    ctx = {
        "request": request,
        "current_user": getattr(request.state, "user", None),
        "csrf_token": ensure_csrf_token(request),
        "app_name": "Enrollment Reservation Management System",
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
