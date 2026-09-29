from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router

app = FastAPI(
    title="QResolve",
    description="AI-powered Quantum Runtime Error Solver",
    version="0.1.0",
)

# CORS is opt-in: set QRESOLVE_CORS_ORIGINS="http://localhost:5173,..." only
# when a frontend is served from a different origin without a dev proxy
# (e.g. static host or Electron). Empty (default) = same-origin only.
_cors_origins = [o.strip() for o in os.environ.get("QRESOLVE_CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

app.include_router(router)


@app.get("/health")
def health():
    from backend.api.solve import supported_frameworks

    return {
        "status": "ok",
        "service": "QResolve",
        "version": "0.1.0",
        "frameworks": supported_frameworks(),
    }

# No "/" route: in the desktop build the root is served by the bundled
# frontend (mounted last by desktop/qresolve_desktop.py).