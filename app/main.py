import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.routers import admin, auth, dashboard, reports, sections, students
from app.security import csrf_token_valid
from app.templating import render

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enrollment.http")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CSRFProtectMiddleware:
    """ASGI middleware verifying CSRF tokens on unsafe methods.

    Buffers the request body so downstream handlers can still parse the form.
    Must run inside SessionMiddleware (i.e., SessionMiddleware added after it).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        buffered: list[dict] = []

        async def buffered_receive():
            message = await receive()
            buffered.append(message)
            return message

        request = Request(scope, buffered_receive)
        form = await request.form()
        session = scope.get("session") or {}
        supplied = request.headers.get("X-CSRF-Token") or form.get("_csrf")
        if not csrf_token_valid(session.get("_csrf_token"), supplied):
            logger.warning(
                "CSRF check failed for %s %s", scope.get("method"), scope.get("path")
            )
            response = HTMLResponse(
                "<h1>403 Forbidden</h1><p>CSRF token missing or invalid.</p>",
                status_code=403,
            )
            await response(scope, receive, send)
            return

        async def replay_receive():
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.debug else None,
    )

    @app.middleware("http")
    async def security_headers_and_logging(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        # Log only method/path/status — never query strings or bodies (may contain personal data).
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    # Pure-ASGI CSRF guard (inside SessionMiddleware so scope["session"] is available).
    # It buffers the request body so the downstream app can still read the form.
    # Note: get_current_user attaches request.state.user for templates.
    app.add_middleware(CSRFProtectMiddleware)

    # Added last so it is the outermost middleware: populates request.session for the rest.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="session",
        https_only=settings.cookie_secure,
        same_site="lax",
        max_age=settings.session_max_age,
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == 401:
            next_url = request.url.path
            if request.url.query:
                next_url += f"?{request.url.query}"
            return RedirectResponse(f"/login?next={next_url}", status_code=303)
        if exc.status_code == 404:
            return render(request, "errors/404.html", {}, status_code=404)
        if exc.status_code == 403:
            return render(request, "errors/403.html", {"detail": exc.detail}, status_code=403)
        return HTMLResponse(
            f"<h1>Error {exc.status_code}</h1><p>{exc.detail}</p>", status_code=exc.status_code
        )

    app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(sections.router)
    app.include_router(students.router)
    app.include_router(reports.router)
    app.include_router(admin.router)

    return app


app = create_app()
