"""FastAPI application: API routes, pages and static assets."""

from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .bootstrap import read_secret_key
from .config import get_settings
from .db import get_db
from .deps import session_user
from .errors import FormError
from .routers import auth, fields, groups, personnel, users

settings = get_settings()
SECRET_KEY = settings.secret_key or read_secret_key()
if not SECRET_KEY:
    raise RuntimeError(
        "No session key. The app generates one on first start; run "
        "'python -m registry.bootstrap' before serving."
    )
PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATE_DIR = PACKAGE_DIR / "templates"


def _asset_version() -> str:
    """Changes whenever a static file changes, so browsers fetch new assets after an update."""
    digest = hashlib.sha256(__version__.encode())
    for path in sorted(STATIC_DIR.rglob("*")):
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _render(name: str) -> str:
    html = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
    return html.replace("{{title}}", escape(settings.app_title)).replace("{{v}}", _asset_version())


INDEX_HTML = _render("index.html")
LOGIN_HTML = _render("login.html")
NO_STORE = {"Cache-Control": "no-store"}

app = FastAPI(
    title="Personnel Registry API",
    version=__version__,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="registry_session",
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=settings.session_https_only,
)

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if not request.url.path.startswith("/api/docs"):  # Swagger UI loads its own assets
        response.headers.setdefault("Content-Security-Policy", CSP)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# ---- error responses: {"detail": "message"} or {"detail": {"message", "fields"}} ----

FRIENDLY_ERRORS = {
    "missing": lambda ctx: "This field is required.",
    "string_too_short": lambda ctx: "This field is required."
    if ctx.get("min_length") == 1
    else f"Use at least {ctx.get('min_length')} characters.",
    "string_too_long": lambda ctx: f"Use {ctx.get('max_length')} characters or fewer.",
    "int_parsing": lambda ctx: "Enter a whole number.",
    "int_type": lambda ctx: "Enter a whole number.",
    "date_parsing": lambda ctx: "Use the format YYYY-MM-DD.",
    "date_from_datetime_parsing": lambda ctx: "Use the format YYYY-MM-DD.",
    "literal_error": lambda ctx: "Choose one of the listed options.",
    "bool_parsing": lambda ctx: "Choose yes or no.",
    "greater_than_equal": lambda ctx: f"Use a number of at least {ctx.get('ge')}.",
    "less_than_equal": lambda ctx: f"Use a number no larger than {ctx.get('le')}.",
}


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields: dict[str, str] = {}
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ()) if part != "body"]
        key = ".".join(loc) or "request"
        ctx = err.get("ctx") or {}
        if err.get("type") == "value_error":
            message = str(ctx.get("error", err.get("msg", "Invalid value.")))
        elif err.get("type") in FRIENDLY_ERRORS:
            message = FRIENDLY_ERRORS[err["type"]](ctx)
        else:
            message = str(err.get("msg", "Invalid value."))
        fields.setdefault(key, message)
    return JSONResponse(
        status_code=422,
        content={"detail": {"message": "Some fields need attention.", "fields": fields}},
    )


@app.exception_handler(FormError)
async def form_error(request: Request, exc: FormError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"message": exc.message, "fields": exc.fields}},
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": "That change conflicts with an existing record. Refresh and try again."},
    )


# ---- routes -----------------------------------------------------------------

for module in (auth, users, groups, fields, personnel):
    app.include_router(module.router)


@app.get("/api/meta", tags=["meta"])
def meta() -> dict:
    return {"title": settings.app_title, "version": __version__, "database": settings.db_engine}


@app.get("/healthz", include_in_schema=False)
def healthz(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "database unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})


@app.get("/", include_in_schema=False)
def index(request: Request, db: Session = Depends(get_db)):
    if session_user(request, db) is None:
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(INDEX_HTML, headers=NO_STORE)


@app.get("/login", include_in_schema=False)
def login_page(request: Request, db: Session = Depends(get_db)):
    if session_user(request, db) is not None:
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(LOGIN_HTML, headers=NO_STORE)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
