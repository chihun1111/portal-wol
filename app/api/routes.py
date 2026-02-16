from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from ..config import probe_online
from ..core.settings import get_settings
from ..services.logs import log_event, read_logs
from ..services.power import execute_target_command, wake_target
from ..services.targets import (
    create_target,
    delete_target,
    get_target_or_404,
    list_targets,
    record_status,
    update_target,
)

router = APIRouter()


def _static_path(*parts: str) -> Path:
    settings = get_settings()
    candidate = settings.static_dir.joinpath(*parts)
    if not candidate.is_file():
        detail = (
            f"Static asset {'/'.join(parts)} not found. "
            "Run scripts/build_frontend.sh to generate the Next.js bundle."
        )
        raise HTTPException(status_code=503, detail=detail)
    return candidate


def _serve_exported_page(name: str) -> FileResponse:
    return FileResponse(_static_path(f"{name}.html"))


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    for name in ("favicon.ico", "favicon.svg"):
        try:
            return FileResponse(_static_path(name))
        except HTTPException:
            continue
    raise HTTPException(status_code=404, detail="Favicon not found")


class WakeBody(BaseModel):
    target: str


class TargetActionBody(BaseModel):
    target: str


class TargetCreateBody(BaseModel):
    name: str
    ip: str
    mac: Optional[str] = None


class TargetUpdateBody(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    mac: Optional[str] = None


@router.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/wol", status_code=307)


@router.get("/wol", include_in_schema=False)
async def wol_page() -> FileResponse:
    return _serve_exported_page("wol")


@router.get("/settings", include_in_schema=False)
async def settings_page() -> FileResponse:
    return _serve_exported_page("settings")


@router.get("/wol.html", include_in_schema=False)
async def legacy_wol_redirect() -> RedirectResponse:
    return RedirectResponse(url="/wol", status_code=307)


@router.get("/settings.html", include_in_schema=False)
async def legacy_settings_redirect() -> RedirectResponse:
    return RedirectResponse(url="/settings", status_code=307)


@router.get("/api/targets")
async def list_targets_api():
    return {"targets": list_targets()}


@router.post("/api/targets")
async def create_target_api(body: TargetCreateBody):
    target = create_target(body.model_dump())
    return {"target": target}


@router.patch("/api/targets/{name}")
async def update_target_api(name: str, body: TargetUpdateBody):
    target = update_target(name, {k: v for k, v in body.model_dump().items() if v is not None})
    return {"target": target}


@router.delete("/api/targets/{name}")
async def delete_target_api(name: str):
    delete_target(name)
    return {"ok": True}


@router.get("/api/status")
async def status(target: str, silent: bool = False):
    info = get_target_or_404(target)
    ip = info.get("ip") or ""
    online = probe_online(ip)
    record_status(info["name"], online, ip)
    if not silent:
        log_event({"evt": "status", "target": target, "online": online})
    return {"target": info["name"], "online": online}


@router.post("/api/wake")
async def wake(body: WakeBody):
    return wake_target(body.target)


@router.post("/api/shutdown")
async def shutdown(body: TargetActionBody):
    return execute_target_command(body.target, "shutdown")


@router.post("/api/reboot")
async def reboot(body: TargetActionBody):
    return execute_target_command(body.target, "reboot")


@router.get("/api/logs")
async def get_logs(limit: int = 200):
    return {"logs": read_logs(limit)}
