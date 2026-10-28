from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.security import get_current_user
from app.services import password_service
from app.templating import render

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/password")
def change_password_page(request: Request, user=Depends(get_current_user)):
    return render(
        request,
        "account/password.html",
        {
            "errors": [],
            "success": None,
            "must_change": user.must_change_password,
        },
    )


@router.post("/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    errors = password_service.change_own_password(
        db,
        user,
        current_password=current_password,
        new_password=new_password,
        confirm_password=confirm_password,
    )
    if errors:
        return render(
            request,
            "account/password.html",
            {"errors": errors, "success": None, "must_change": user.must_change_password},
            status_code=400,
        )
    password_service.regenerate_session_after_password_change(request, user)
    return render(
        request,
        "account/password.html",
        {
            "errors": [],
            "success": "Password changed successfully.",
            "must_change": False,
        },
    )
