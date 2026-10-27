from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import Role, User
from app.security import require_admin
from app.services import auth_service
from app.templating import render

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("")
def list_users_page(request: Request, db: Session = Depends(get_db), admin=Depends(require_admin)):
    users = list(db.scalars(select(User).order_by(User.email)))
    return render(request, "admin/users.html", {"users": users})


@router.get("/new")
def new_user_page(request: Request, admin=Depends(require_admin)):
    return render(request, "admin/user_form.html", {"errors": []})


@router.post("/new")
def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    role: str = Form("faculty"),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    try:
        role_enum = Role(role)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role.")
    user, errors = auth_service.create_user(
        db, email=email, full_name=full_name, password=password, role=role_enum
    )
    if errors:
        return render(
            request,
            "admin/user_form.html",
            {"errors": errors, "form": {"email": email, "full_name": full_name, "role": role}},
            status_code=400,
        )
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/{user_id}/toggle")
def toggle_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
    auth_service.set_user_active(db, user, not user.is_active)
    return RedirectResponse("/admin/users", status_code=303)
