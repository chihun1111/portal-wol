from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


async def tailscale_identity_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        identity = request.headers.get("Tailscale-User-Login", "").strip()
        if not identity:
            return JSONResponse(
                status_code=401,
                content={"detail": {"error": "tailscale_identity_required"}},
            )
        request.state.tailscale_user = identity
    return await call_next(request)
