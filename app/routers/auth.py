from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user
from app.services import auth_service
from app.templating import render

router = APIRouter(tags=["auth"])


@router.get("/login")
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return render(request, "login.html", {"error": None})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = auth_service.authenticate(db, email=email, password=password)
    if user is None:
        return render(
            request,
            "login.html",
            {"error": "Invalid email or password."},
            status_code=401,
        )
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request, user=Depends(get_current_user)):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
