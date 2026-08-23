from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .core.auth import tailscale_identity_middleware
from .core.settings import get_settings
from .services.boot_jobs import BootJobManager

# Load .env if present before evaluating settings
load_dotenv()


def _mount_static_assets(app: FastAPI) -> None:
    static_dir = get_settings().static_dir
    if not static_dir.exists():
        return
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")
    app.mount("/app/static", StaticFiles(directory=static_dir, html=True), name="static-legacy")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")


def create_app() -> FastAPI:
    boot_jobs = BootJobManager()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        boot_jobs.startup()
        try:
            yield
        finally:
            boot_jobs.shutdown()

    app = FastAPI(title="WOL-Web", version="1.1.0", lifespan=lifespan)
    app.state.boot_jobs = boot_jobs
    app.middleware("http")(tailscale_identity_middleware)
    app.include_router(router)
    _mount_static_assets(app)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
