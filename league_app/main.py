import logging
import sys
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import Base, get_async_engine
from .api import router
from .realtime.router import router as ws_router

# Ensure all ORM models are loaded so SQLAlchemy can resolve relationships
import league_app.api.users.model  # noqa: F401
import league_app.api.players.model  # noqa: F401
import league_app.api.teams.model  # noqa: F401
import league_app.api.tournaments.model  # noqa: F401
import league_app.api.matches.model  # noqa: F401
import league_app.api.stages.model  # noqa: F401
import league_app.api.tables.model  # noqa: F401
import league_app.api.leagues.model  # noqa: F401

FAVICON_PATH = "static/favicon.ico"

# --- Logging ---
_settings = get_settings()
_log_level = getattr(logging, getattr(_settings, "LOG_LEVEL", "INFO"), logging.INFO)
_log_file = getattr(_settings, "LOG_FILE", "")
_handlers: list[logging.Handler] = []
_formatter = logging.Formatter(
    "%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Always log to stderr (visible in terminal / journald)
_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setFormatter(_formatter)
_handlers.append(_stderr_handler)

# Optionally log to file (set LOG_FILE in .env)
if _log_file:
    _file_handler = logging.FileHandler(_log_file, encoding="utf-8")
    _file_handler.setFormatter(_formatter)
    _handlers.append(_file_handler)

logging.basicConfig(level=_log_level, handlers=_handlers)
logger = logging.getLogger("foosball")
logger.setLevel(_log_level)
# Quiet down noisy libraries
logging.getLogger("passlib").setLevel(logging.WARNING)
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(
    logging.INFO if _log_level <= logging.DEBUG else logging.WARNING
)
# Prevent duplicate uvicorn lines (uvicorn has its own formatter)
for _uv_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_uv_name).handlers = []
    logging.getLogger(_uv_name).propagate = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

settings = get_settings()
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if origins:
    allow_all = origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not allow_all,  # credentials + wildcard origin is forbidden by spec
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(router)
app.include_router(ws_router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(FAVICON_PATH)


# --- Serve frontend (PWA) ---
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if _FRONTEND_DIR.is_dir():
    # Serve sw.js and manifest.json from root (required for PWA scope)
    @app.get("/sw.js", include_in_schema=False)
    async def service_worker():
        return FileResponse(
            _FRONTEND_DIR / "sw.js", media_type="application/javascript",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/manifest.json", include_in_schema=False)
    async def manifest():
        return FileResponse(_FRONTEND_DIR / "manifest.json", media_type="application/json")

    # Static assets (css, js, icons)
    app.mount("/css", StaticFiles(directory=_FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=_FRONTEND_DIR / "js"), name="js")
    app.mount("/icons", StaticFiles(directory=_FRONTEND_DIR / "icons"), name="icons")

    # Prevent browsers/proxies from caching JS/CSS/sw.js
    @app.middleware("http")
    async def no_cache_static(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith(("/js/", "/css/")) or path == "/sw.js":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

    # SPA fallback: serve index.html for all non-API routes

    @app.get("/", include_in_schema=False)
    async def spa_root():
        return FileResponse(_FRONTEND_DIR / "index.html")

    @app.middleware("http")
    async def spa_fallback_middleware(request, call_next):
        response = await call_next(request)
        path = request.url.path
        # If no API route matched (404) and it's not an API/ws/docs path,
        # serve index.html for SPA client-side routing
        if (
            response.status_code == 404
            and request.method == "GET"
            and not path.startswith(("/api/", "/v1/", "/ws/", "/docs", "/redoc", "/openapi"))
        ):
            return FileResponse(_FRONTEND_DIR / "index.html")
        return response
