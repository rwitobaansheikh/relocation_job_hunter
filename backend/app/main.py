import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routes import auth_router, router
from app.routes_admin import admin_router
from app.routes_billing import billing_router, webhook_router
from app.routes_oauth import oauth_router
from app.services.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.uploads_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.generated_dir).mkdir(parents=True, exist_ok=True)
    init_db()
    logger.info("Database initialized")
    logger.info(
        "LLM provider=%s model=%s",
        settings.llm_provider,
        settings.ollama_model if settings.llm_provider == "ollama" else settings.gemini_model,
    )
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Job Application Flow",
    description="Automated job search, tailoring, and outreach for relocation-friendly roles",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(router)
app.include_router(admin_router)
app.include_router(billing_router)
app.include_router(webhook_router)
app.include_router(oauth_router)


@app.get("/health")
async def health():
    from app.services.llm import llm_health

    llm = await llm_health()
    overall = "ok" if llm.get("status") in ("ok", "configured") else "degraded"
    return {"status": overall, "llm": llm}


# Serve the built React frontend (if present) from the same origin as the API.
# In production the Docker image copies the Vite build into settings.static_dir;
# in local dev this directory won't exist and the Vite dev server is used instead.
_static_dir = Path(settings.static_dir)
if _static_dir.is_dir():
    _assets_dir = _static_dir / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    _index_file = _static_dir / "index.html"

    @app.get("/", include_in_schema=False)
    async def _serve_index():
        return FileResponse(_index_file)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _serve_spa(full_path: str):
        # Let unmatched API/health calls 404 as JSON instead of returning the SPA.
        if full_path.startswith(("api/", "api", "health")):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = _static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        # Unknown client-side route -> let React Router handle it.
        return FileResponse(_index_file)
else:
    logger.info("Static dir %s not found; serving API only (dev mode)", _static_dir)
