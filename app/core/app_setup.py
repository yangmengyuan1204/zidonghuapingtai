import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .utils import BASE_DIR, STATIC_DIR


def create_app(*, lifespan: Any) -> FastAPI:
    disable_docs = os.getenv("DISABLE_OPENAPI", "").strip() in {"1", "true", "yes"}
    return FastAPI(
        title="API + UI automation test platform",
        lifespan=lifespan,
        docs_url=None if disable_docs else "/docs",
        redoc_url=None if disable_docs else "/redoc",
        openapi_url=None if disable_docs else "/openapi.json",
    )


def configure_app(app: FastAPI) -> None:
    cors_origins = os.getenv("CORS_ORIGINS", "").strip()
    allowed_origins = (
        [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
        if cors_origins
        else ["http://localhost:8000", "http://127.0.0.1:8000"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        return response

    @app.middleware("http")
    async def no_cache_frontend_assets(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/static/"):
            if "Cache-Control" not in response.headers:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path == "/":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type and "charset" not in content_type.lower():
            response.headers["content-type"] = content_type.replace("application/json", "application/json; charset=utf-8")
        return response

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    report_dir = BASE_DIR / "reports"
    if report_dir.exists():
        app.mount("/reports", StaticFiles(directory=str(report_dir)), name="reports")
