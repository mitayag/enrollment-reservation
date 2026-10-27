from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user
from app.services import section_service, student_service
from app.templating import render

router = APIRouter(prefix="/students", tags=["students"])


def _form_context(form: dict | None = None) -> dict:
    return {"form": form or {}}


@router.get("")
def list_students_page(
    request: Request,
    q: str | None = None,
    section_id: int | None = None,
    year_level: int | None = None,
    page: int = 1,
    show_deleted: bool = False,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    include_deleted = show_deleted and user.role.value == "admin"
    students, total = student_service.list_students(
        db,
        q=q,
        section_id=section_id,
        year_level=year_level,
        include_deleted=include_deleted,
        page=page,
    )
    sections = section_service.list_sections(db, active_only=True)
    total_pages = max((total + student_service.PAGE_SIZE - 1) // student_service.PAGE_SIZE, 1)
    return render(
        request,
        "students/list.html",
        {
            "students": students,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "sections": sections,
            "q": q or "",
            "section_id": section_id,
            "year_level": year_level,
            "include_deleted": include_deleted,
        },
    )


@router.get("/new")
def new_student_page(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sections = section_service.list_sections(db, active_only=True)
    return render(request, "students/form.html", {"student": None, "sections": sections, "errors": []})


@router.post("/new")
def create_student(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    middle_initial: str = Form(""),
    telephone: str = Form(""),
    email: str = Form(""),
    section_id: int = Form(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    student, errors = student_service.create_student(
        db,
        first_name=first_name,
        last_name=last_name,
        middle_initial=middle_initial,
        telephone=telephone,
        email=email,
        section_id=section_id,
        created_by=user.id,
    )
    sections = section_service.list_sections(db, active_only=True)
    if errors:
        return render(
            request,
            "students/form.html",
            {
                "student": None,
                "sections": sections,
                "errors": errors,
                "form": {
                    "first_name": first_name,
                    "last_name": last_name,
                    "middle_initial": middle_initial,
                    "telephone": telephone,
                    "email": email,
                    "section_id": section_id,
                },
            },
            status_code=400,
        )
    return RedirectResponse("/students", status_code=303)


@router.get("/{student_id}/edit")
def edit_student_page(
    student_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    student = student_service.get_student(db, student_id)
    if student is None or (student.is_deleted and user.role.value != "admin"):
        raise HTTPException(status_code=404)
    if not student_service.can_modify(user, student):
        raise HTTPException(status_code=403)
    sections = section_service.list_sections(db, active_only=True)
    if student.section and not student.section.is_active and student.section not in sections:
        sections = [student.section, *sections]
    return render(request, "students/form.html", {"student": student, "sections": sections, "errors": []})


@router.post("/{student_id}/edit")
def update_student(
    student_id: int,
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    middle_initial: str = Form(""),
    telephone: str = Form(""),
    email: str = Form(""),
    section_id: int = Form(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    student = student_service.get_student(db, student_id)
    if student is None or student.is_deleted:
        raise HTTPException(status_code=404)
    if not student_service.can_modify(user, student):
        raise HTTPException(status_code=403)
    student, errors = student_service.update_student(
        db,
        student,
        first_name=first_name,
        last_name=last_name,
        middle_initial=middle_initial,
        telephone=telephone,
        email=email,
        section_id=section_id,
    )
    sections = section_service.list_sections(db, active_only=True)
    if errors:
        return render(
            request,
            "students/form.html",
            {
                "student": student,
                "sections": sections,
                "errors": errors,
                "form": {
                    "first_name": first_name,
                    "last_name": last_name,
                    "middle_initial": middle_initial,
                    "telephone": telephone,
                    "email": email,
                    "section_id": section_id,
                },
            },
            status_code=400,
        )
    return RedirectResponse("/students", status_code=303)


@router.post("/{student_id}/delete")
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    student = student_service.get_student(db, student_id)
    if student is None or student.is_deleted:
        raise HTTPException(status_code=404)
    if not student_service.can_modify(user, student):
        raise HTTPException(status_code=403)
    student_service.soft_delete_student(db, student)
    return RedirectResponse("/students", status_code=303)
