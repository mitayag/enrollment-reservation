from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user, require_admin
from app.services import program_service, section_service
from app.templating import render

router = APIRouter(prefix="/sections", tags=["sections"])


def _parse_program_id(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    return int(value) if value.isdigit() and int(value) > 0 else None


@router.get("")
def list_sections_page(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sections = section_service.list_sections(db)
    counts = {s.id: section_service.student_count_by_section(db, s.id) for s in sections}
    unassigned = section_service.unassigned_count(db)
    return render(
        request,
        "sections/list.html",
        {"sections": sections, "counts": counts, "unassigned_count": unassigned},
    )


@router.get("/new")
def new_section_page(request: Request, db: Session = Depends(get_db), user=Depends(require_admin)):
    programs = program_service.list_programs(db, active_only=True)
    return render(
        request, "sections/form.html", {"section": None, "errors": [], "programs": programs}
    )


@router.post("/new")
def create_section(
    request: Request,
    name: str = Form(...),
    year_level: int = Form(...),
    program_id: str = Form(""),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    program = _parse_program_id(program_id)
    section, errors = section_service.create_section(
        db, name=name, year_level=year_level, program_id=program, created_by=admin.id
    )
    if errors:
        programs = program_service.list_programs(db, active_only=True)
        return render(
            request,
            "sections/form.html",
            {
                "section": None,
                "errors": errors,
                "programs": programs,
                "form": {"name": name, "year_level": year_level, "program_id": program},
            },
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
    programs = program_service.list_programs(db)
    return render(
        request, "sections/form.html", {"section": section, "errors": [], "programs": programs}
    )


@router.post("/{section_id}/edit")
def update_section(
    section_id: int,
    request: Request,
    name: str = Form(...),
    year_level: int = Form(...),
    program_id: str = Form(""),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    section = section_service.get_section(db, section_id)
    if section is None:
        raise HTTPException(status_code=404)
    program = _parse_program_id(program_id)
    section, errors = section_service.update_section(
        db, section, name=name, year_level=year_level, program_id=program
    )
    if errors:
        programs = program_service.list_programs(db)
        return render(
            request,
            "sections/form.html",
            {
                "section": section,
                "errors": errors,
                "programs": programs,
                "form": {"name": name, "year_level": year_level, "program_id": program},
            },
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
