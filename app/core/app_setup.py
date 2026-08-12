import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .utils import BASE_DIR, STATIC_DIR


def create_app(*, lifespan: Any) -> FastAPI:
    disable_docs = os.getenv("DISABLE_OPENAPI", "").strip() in {"1", "true", "yes"}
    return FastAPI(
        title="接口 + UI 自动化测试平台",
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
            # HTML/JSON must not be immutable-cached — admin pages (返回平台) are edited in place
            if path.endswith((".html", ".htm", ".json")):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            elif "Cache-Control" not in response.headers:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path == "/":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type and "charset" not in content_type.lower():
            response.headers["content-type"] = content_type.replace("application/json", "application/json; charset=utf-8")
        return response

    favicon_path = BASE_DIR / "frontend" / "public" / "favicon.ico"

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(favicon_path, media_type="image/vnd.microsoft.icon")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    report_dir = BASE_DIR / "reports"
    if report_dir.exists():
        app.mount("/reports", StaticFiles(directory=str(report_dir)), name="reports")

    # Vue3 迁移工程挂载（Phase 0）
    # 仅新增，不修改任何已有路由
    # frontend/dist 不存在时跳过，不影响旧应用
    # 使用自定义路由 + StaticFiles 支持 SPA History 模式 fallback
    frontend_dist = BASE_DIR / "frontend" / "dist"
    if frontend_dist.exists():
        from fastapi import Response
        from starlette.requests import Request

        v3_static = StaticFiles(directory=str(frontend_dist))

        @app.get("/v3", include_in_schema=False)
        @app.get("/v3/", include_in_schema=False)
        async def _v3_index(request: Request):
            """根路径 /v3/ 返回 index.html"""
            index_path = frontend_dist / "index.html"
            return Response(content=index_path.read_bytes(), media_type="text/html")

        @app.get("/v3/{path:path}", include_in_schema=False)
        async def _v3_assets(request: Request, path: str):
            """静态资源 /v3/assets/xxx 直接返回文件；非文件路径回退到 index.html（SPA History 模式）"""
            full = frontend_dist / path
            if full.is_file():
                # 修复：传入 request.scope，避免 Starlette StaticFiles.get_response 读取 scope["method"] 时 KeyError
                return await v3_static.get_response(path, request.scope)
            index_path = frontend_dist / "index.html"
            return Response(content=index_path.read_bytes(), media_type="text/html")
