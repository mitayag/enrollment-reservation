from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.section import Section
from app.security import get_current_user, require_admin
from app.services import section_service
from app.templating import render

router = APIRouter(prefix="/sections", tags=["sections"])


@router.get("")
def list_sections_page(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sections = section_service.list_sections(db)
    counts = {s.id: section_service.student_count_by_section(db, s.id) for s in sections}
    return render(request, "sections/list.html", {"sections": sections, "counts": counts})


@router.get("/new")
def new_section_page(request: Request, user=Depends(require_admin)):
    return render(request, "sections/form.html", {"section": None, "errors": []})


@router.post("/new")
def create_section(
    request: Request,
    name: str = Form(...),
    year_level: int = Form(...),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    section, errors = section_service.create_section(
        db, name=name, year_level=year_level, created_by=admin.id
    )
    if errors:
        return render(
            request,
            "sections/form.html",
            {"section": None, "errors": errors, "form": {"name": name, "year_level": year_level}},
            status_code=400,
        )
    return RedirectResponse("/sections", status_code=303)


@router.get("/{section_id}/edit")
def edit_section_page(
    section_id: int, request: Request, db: Session = Depends(get_db), user=Depends(require_admin)
):
    section = section_service.get_section(db, section_id)
    if section is None:
        raise HTTPException(status_code=404)
    return render(request, "sections/form.html", {"section": section, "errors": []})


@router.post("/{section_id}/edit")
def update_section(
    section_id: int,
    request: Request,
    name: str = Form(...),
    year_level: int = Form(...),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    section = section_service.get_section(db, section_id)
    if section is None:
        raise HTTPException(status_code=404)
    section, errors = section_service.update_section(
        db, section, name=name, year_level=year_level
    )
    if errors:
        return render(
            request,
            "sections/form.html",
            {"section": section, "errors": errors, "form": {"name": name, "year_level": year_level}},
            status_code=400,
        )
    return RedirectResponse("/sections", status_code=303)


@router.post("/{section_id}/toggle")
def toggle_section(
    section_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    section = section_service.get_section(db, section_id)
    if section is None:
        raise HTTPException(status_code=404)
    try:
        section_service.set_section_active(db, section, not section.is_active)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse("/sections", status_code=303)
