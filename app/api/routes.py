from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from ..config import probe_online
from ..core.settings import get_settings
from ..services.logs import log_event, read_logs
from ..services.boot_jobs import ActiveBootJobError, BootJobNotCancellableError
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


@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}


@router.get("/wol.html", include_in_schema=False)
async def legacy_wol_redirect() -> RedirectResponse:
    return RedirectResponse(url="/wol", status_code=307)


@router.get("/settings.html", include_in_schema=False)
async def legacy_settings_redirect() -> RedirectResponse:
    return RedirectResponse(url="/settings", status_code=307)


@router.get("/api/targets")
def list_targets_api():
    settings = get_settings()
    targets = list_targets()
    for target in targets:
        target["can_boot_ubuntu"] = bool(
            settings.ubuntu_boot_enabled
            and target.get("name") == settings.ubuntu_boot_target
        )
    return {"targets": targets}


@router.post("/api/targets")
def create_target_api(body: TargetCreateBody):
    target = create_target(body.model_dump())
    return {"target": target}


@router.patch("/api/targets/{name}")
def update_target_api(name: str, body: TargetUpdateBody, request: Request):
    with request.app.state.boot_jobs.power_action(name) as canonical_name:
        target = update_target(canonical_name, body.model_dump(exclude_unset=True))
    return {"target": target}


@router.delete("/api/targets/{name}")
def delete_target_api(name: str, request: Request):
    with request.app.state.boot_jobs.power_action(name) as canonical_name:
        delete_target(canonical_name)
    return {"ok": True}


@router.get("/api/status")
def status(target: str, silent: bool = False):
    info = get_target_or_404(target)
    ip = info.get("ip") or ""
    online = probe_online(ip)
    record_status(info["name"], online, ip)
    if not silent:
        log_event({"evt": "status", "target": target, "online": online})
    return {"target": info["name"], "online": online}


@router.post("/api/wake")
def wake(body: WakeBody, request: Request):
    with request.app.state.boot_jobs.power_action(body.target) as target:
        return wake_target(target)


@router.post("/api/shutdown")
def shutdown(body: TargetActionBody, request: Request):
    with request.app.state.boot_jobs.power_action(body.target) as target:
        return execute_target_command(target, "shutdown")


@router.post("/api/reboot")
def reboot(body: TargetActionBody, request: Request):
    with request.app.state.boot_jobs.power_action(body.target) as target:
        return execute_target_command(target, "reboot")


@router.post("/api/boot/ubuntu", status_code=202)
def boot_ubuntu(body: TargetActionBody, request: Request):
    actor = request.state.tailscale_user
    try:
        job = request.app.state.boot_jobs.create_job(body.target, actor)
    except ActiveBootJobError as exc:
        raise HTTPException(
            409,
            detail={"error": "active_boot_job", "job": exc.job},
        ) from exc
    return {"job": job}


@router.get("/api/jobs")
def list_jobs_api(request: Request, target: Optional[str] = None, limit: int = 20):
    return {"jobs": request.app.state.boot_jobs.list_jobs(target=target, limit=limit)}


@router.get("/api/jobs/{job_id}")
def get_job_api(job_id: str, request: Request):
    return {"job": request.app.state.boot_jobs.get_job(job_id)}


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job_api(job_id: str, request: Request):
    try:
        job = request.app.state.boot_jobs.cancel_job(job_id)
    except BootJobNotCancellableError as exc:
        raise HTTPException(409, detail={"error": "job_not_cancellable"}) from exc
    return {"job": job}


@router.get("/api/logs")
def get_logs(limit: int = 200):
    return {"logs": read_logs(limit)}
