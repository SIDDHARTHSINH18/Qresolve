"""QResolve desktop launcher (Windows EXE entry point).

Serves the built frontend and the API from one process on one dedicated
port (default 127.0.0.1:8321 — never 8000, which belongs to ENMA), runs a
startup health check, and opens the system browser. On any failure it
reports the concrete problem (port conflict, missing frontend build,
failed health check, missing sandbox interpreter) instead of silently
changing ports or starting half-broken.

For PyInstaller's sandboxed child interpreter, see backend/ports.py and
backend/sandbox/executor._interpreter (QRESOLVE_SANDBOX_PYTHON).
"""
from __future__ import annotations

import os
import sys
import threading
import time
import urllib.request
import webbrowser

BACKEND_HOST = "127.0.0.1"
HEALTH_TIMEOUT_S = 25.0

if not getattr(sys, "frozen", False):  # dev mode: make `backend` importable
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _fail(message: str) -> int:
    print(f"[QResolve] {message}", file=sys.stderr)
    _show_dialog("QResolve could not start", message)
    return 1


def _show_dialog(title: str, message: str) -> None:
    """Best-effort visible error for a double-clicked windowless exe."""
    if not getattr(sys, "frozen", False):
        return
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        pass


def _resource_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _frontend_dist() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(_resource_dir(), "web")
    return os.path.join(_resource_dir(), "frontend", "dist")


def _bundled_python() -> str | None:
    """Interpreter shipped next to the exe for sandboxed user code."""
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.dirname(sys.executable), "_python")
        for candidate in (
            os.path.join(base, "python.exe"),               # embeddable layout
            os.path.join(base, "Scripts", "python.exe"),    # venv layout
        ):
            if os.path.isfile(candidate):
                return candidate
    return None


def _wait_for_health(url: str) -> bool:
    deadline = time.monotonic() + HEALTH_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def main() -> int:
    from backend.ports import (
        PortConflictError,
        backend_port_from_env,
        ensure_port_free,
    )

    try:
        port = backend_port_from_env()
        ensure_port_free(port)
    except PortConflictError as exc:
        return _fail(str(exc))

    dist = _frontend_dist()
    if not os.path.isfile(os.path.join(dist, "index.html")):
        return _fail(
            f"Frontend build not found at {dist}. Package 'frontend/dist' into the "
            "application before building the exe."
        )

    sandbox_python = os.environ.get("QRESOLVE_SANDBOX_PYTHON") or _bundled_python()
    if getattr(sys, "frozen", False):
        if not sandbox_python or not os.path.isfile(sandbox_python):
            return _fail(
                "The bundled sandbox interpreter (_python) is missing next to QResolve.exe; "
                "quantum code could not be executed. Reinstall the application."
            )
        os.environ["QRESOLVE_SANDBOX_PYTHON"] = sandbox_python

    import uvicorn

    from backend.main import app
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=dist, html=True), name="qresolve-ui")

    base = f"http://{BACKEND_HOST}:{port}"
    print(f"[QResolve] serving UI + API at {base} (sandbox python: {sandbox_python or sys.executable})")

    def _open_when_ready() -> None:
        if _wait_for_health(base + "/health"):
            webbrowser.open(base + "/")
        else:
            print("[QResolve] health check failed; the UI stays closed", file=sys.stderr)

    threading.Thread(target=_open_when_ready, daemon=True).start()

    try:
        uvicorn.run(app, host=BACKEND_HOST, port=port, log_level="warning")
    except Exception as exc:
        return _fail(f"Backend stopped: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
