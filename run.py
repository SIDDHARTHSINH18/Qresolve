"""QResolve backend launcher with an explicit port policy.

Refuses to start on a colliding or reserved port instead of silently moving
(see backend/ports.py). For development and as the backend entry point of
the packaged desktop app.
"""
from __future__ import annotations

import sys


def main() -> int:
    from backend.ports import (
        BACKEND_HOST,
        ENMA_BACKEND_PORT,
        PortConflictError,
        backend_port_from_env,
        ensure_port_free,
    )

    try:
        port = backend_port_from_env()
        ensure_port_free(port)
    except PortConflictError as exc:
        print(f"[QResolve] {exc}", file=sys.stderr)
        return 2

    import uvicorn

    from backend.main import app

    print(
        f"[QResolve] backend serving on http://{BACKEND_HOST}:{port} "
        f"(port {ENMA_BACKEND_PORT} is reserved for ENMA and never used here)"
    )
    uvicorn.run(app, host=BACKEND_HOST, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
