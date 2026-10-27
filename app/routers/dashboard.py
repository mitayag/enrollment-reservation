from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.section import Section
from app.models.student import Student
from app.security import get_current_user, manila_today_bounds_utc
from app.templating import render

router = APIRouter(tags=["dashboard"])


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    active_students = (
        db.scalar(
            select(func.count(Student.id)).where(Student.deleted_at.is_(None))
        )
        or 0
    )
    active_sections = (
        db.scalar(select(func.count(Section.id)).where(Section.is_active.is_(True))) or 0
    )
    start_utc, end_utc = manila_today_bounds_utc()
    encoded_today = (
        db.scalar(
            select(func.count(Student.id)).where(
                Student.deleted_at.is_(None),
                Student.created_at >= start_utc,
                Student.created_at < end_utc,
            )
        )
        or 0
    )
    return render(
        request,
        "dashboard.html",
        {
            "active_students": active_students,
            "active_sections": active_sections,
            "encoded_today": encoded_today,
        },
    )
