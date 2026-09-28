"""QResolve desktop launcher — windowed (no console) Windows entry point.

Startup state machine (M6 §6):
    STARTING -> CHECK PORT -> PORT AVAILABLE -> START BACKEND
    -> WAIT FOR HEALTH -> HEALTHY -> OPEN UI -> RUNNING
Any failure surfaces a GUI error dialog and a clean, owned shutdown —
never a hidden retry on a different port, never a half-open UI.

UI + API are served same-origin from one process on 127.0.0.1:8321 (the
M5 architecture): the built frontend is mounted at "/" on the FastAPI app.
Sandboxed user code still runs in separate child interpreters (M6 §10);
backend/sandbox/executor.terminate_active_children() gives the launcher an
ownership-explicit shutdown (M6 §7/§8) — it only ever touches children this
process started.
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
import urllib.request
import webbrowser

BACKEND_HOST = "127.0.0.1"
HEALTH_TIMEOUT_S = 25.0
SHUTDOWN_JOIN_S = 6.0

PHASES = (
    "STARTING",
    "CHECK PORT",
    "PORT AVAILABLE",
    "START BACKEND",
    "WAIT FOR HEALTH",
    "HEALTHY",
    "OPEN UI",
    "RUNNING",
)

if not getattr(sys, "frozen", False):  # dev mode: make `backend` importable
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _log(message: str) -> None:
    # A windowed (console=False) build has no stdout; keep the print guarded so
    # it can never raise there.
    try:
        print(f"[QResolve] {message}", file=sys.stderr)
    except Exception:
        pass


def _show_dialog(title: str, message: str) -> None:
    """Visible GUI error — always shown, frozen or not (M6 §4)."""
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        _log(f"{title}: {message}")


def _fail(message: str) -> int:
    _log(f"FATAL: {message}")
    _show_dialog("QResolve could not start", message)
    return 1


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


def _health_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def _wait_for_health(url: str, stop: threading.Event) -> bool:
    deadline = time.monotonic() + HEALTH_TIMEOUT_S
    while time.monotonic() < deadline and not stop.is_set():
        if _health_ok(url):
            return True
        stop.wait(0.3)
    return False


# Bundled frameworks whose first cold import can exceed the user sandbox
# timeout. pennylane is the confirmed offender (~62s cold vs the 30s limit);
# it is warmed first. qiskit/cirq are warmed too so a slow-disk first run of
# any framework stays within budget.
_WARM_FRAMEWORKS = ("pennylane", "qiskit", "cirq")


def _warm_sandbox() -> None:
    """Pre-warm the embedded interpreter's cold imports in the background.

    Runs each framework's import once through the normal isolated sandbox (same
    -I flag, env allowlist, temp dir, output caps) with a one-time longer budget
    so the OS page cache is warm before the user's first solve. Never raises;
    a failed warm-up simply leaves that framework to import cold on first use.
    """
    try:
        from backend.sandbox.executor import run_python_code
        from backend.sandbox.limits import MAX_TIMEOUT_S, SandboxLimits

        warm_limits = SandboxLimits(timeout_s=MAX_TIMEOUT_S)
    except Exception as exc:  # pragma: no cover - defensive
        _log(f"warm-up unavailable: {exc}")
        return

    for module in _WARM_FRAMEWORKS:
        try:
            run_python_code(f"import {module}\n", limits=warm_limits)
            _log(f"warm-up done: {module}")
        except Exception as exc:
            _log(f"warm-up failed for {module}: {exc}")


def main() -> int:
    from backend.ports import (
        PortConflictError,
        backend_port_from_env,
        ensure_port_free,
    )

    events: queue.Queue = queue.Queue()
    stop_health = threading.Event()

    try:
        port = backend_port_from_env()
        ensure_port_free(port)
    except PortConflictError as exc:
        return _fail(str(exc))

    dist = _frontend_dist()
    if not os.path.isfile(os.path.join(dist, "index.html")):
        return _fail(
            f"The QResolve interface files were not found inside the installation.\n"
            "Reinstall the application from QResolve Setup."
        )

    sandbox_python = os.environ.get("QRESOLVE_SANDBOX_PYTHON") or _bundled_python()
    if getattr(sys, "frozen", False):
        if not sandbox_python or not os.path.isfile(sandbox_python):
            return _fail(
                "The bundled quantum runtime (_python) is missing next to QResolve.exe; "
                "code could not be executed.\nReinstall the application from QResolve Setup."
            )
        os.environ["QRESOLVE_SANDBOX_PYTHON"] = sandbox_python

    import uvicorn

    from backend.main import app
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=dist, html=True), name="qresolve-ui")
    config = uvicorn.Config(
        app, host=BACKEND_HOST, port=port,
        # log_config=None: uvicorn's default formatter probes sys.stderr.isatty(),
        # but a windowed (console=False) build has sys.stderr == None and the
        # whole app dies during logging setup. Keep uvicorn off the log config.
        log_config=None,
        timeout_graceful_shutdown=3,
    )
    server = uvicorn.Server(config)
    base = f"http://{BACKEND_HOST}:{port}"
    _log(f"serving UI + API at {base} (sandbox python: {sandbox_python or sys.executable})")

    def _serve() -> None:
        try:
            server.run()
        except BaseException as exc:  # surface bind/loop failures
            _log(f"backend thread error: {type(exc).__name__}: {exc}")
            events.put(("fatal", f"QResolve's backend stopped unexpectedly:\n{exc}"))

    def _readiness() -> None:
        if _wait_for_health(base + "/health", stop_health):
            events.put(("phase", "HEALTHY"))
            events.put(("phase", "OPEN UI"))
            webbrowser.open(base + "/")
            events.put(("phase", "RUNNING"))
        else:
            events.put((
                "fatal",
                f"The QResolve backend did not become ready on port {port}.\n"
                "Close the application using this port and try again.",
            ))

    backend_thread = threading.Thread(target=_serve, name="qresolve-backend", daemon=True)
    events.put(("phase", "PORT AVAILABLE"))
    events.put(("phase", "START BACKEND"))
    events.put(("phase", "WAIT FOR HEALTH"))
    backend_thread.start()
    threading.Thread(target=_readiness, name="qresolve-readiness", daemon=True).start()

    if getattr(sys, "frozen", False):
        # A cold OS page cache makes the embedded interpreter's first import of a
        # heavy framework (pennylane ~62s, qiskit/cirq similar) exceed the 30s
        # user sandbox timeout, killing the child before it writes a result. Pre-
        # warm each bundled framework once, in the background, through the same
        # isolated sandbox path so the first real user solve runs warm (~2.5s).
        # The user-facing 30s timeout is NOT changed; only this one-time warm-up
        # uses a longer budget.
        threading.Thread(target=_warm_sandbox, name="qresolve-warmup", daemon=True).start()

    def _shutdown() -> None:
        stop_health.set()
        server.should_exit = True
        backend_thread.join(SHUTDOWN_JOIN_S)
        from backend.sandbox.executor import terminate_active_children

        terminate_active_children()  # owned sandbox interpreters only (M6 §8)

    try:
        return _run_gui(events, base, _shutdown)
    except KeyboardInterrupt:
        _shutdown()
        return 0


def _run_gui(events: queue.Queue, base: str, shutdown) -> int:
    """Tkinter status window + event pump. Returns the process exit code.

    Passive on purpose: _readiness() already opens the UI in the browser once
    the backend is healthy, so this window only reports progress and remains
    the single quit affordance — closing it shuts QResolve down.
    """
    import tkinter
    from tkinter import messagebox

    exit_code = 0
    root = tkinter.Tk()
    root.title("QResolve")
    root.geometry("460x170")
    root.resizable(False, False)

    status = tkinter.StringVar(value="STARTING")
    tkinter.Label(root, text="QResolve — quantum code debugger",
                  font=("Segoe UI", 11, "bold")).pack(pady=(18, 4))
    tkinter.Label(root, textvariable=status, wraplength=420, justify="left").pack(pady=2)

    def _pump() -> None:
        nonlocal exit_code
        try:
            while True:
                kind, payload = events.get_nowait()
                if kind == "phase":
                    if payload == "RUNNING":
                        status.set(f"Running at {base}\nClose this window to quit QResolve.")
                    else:
                        status.set(payload)
                elif kind == "fatal":
                    exit_code = 1
                    shutdown()
                    messagebox.showerror("QResolve could not start", payload)
                    root.destroy()
                    return
        except queue.Empty:
            pass
        root.after(100, _pump)

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.after(100, _pump)
    root.mainloop()
    shutdown()
    return exit_code


def _crash_log_path() -> str:
    """Where a startup crash is written.

    Never next to the executable: an installed app lives in a protected
    directory a standard user cannot write to (M7 section 6).
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "QResolve", "QResolve-startup-error.log")


if __name__ == "__main__":
    try:
        _code = main()
    except BaseException:  # never die via the bootloader's bare traceback box
        import traceback

        _tb = traceback.format_exc()
        _log(_tb)
        if getattr(sys, "frozen", False):
            try:
                path = _crash_log_path()
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as _f:
                    _f.write(_tb)
            except OSError:
                pass
        _show_dialog("QResolve could not start", _tb[-1500:])
        _code = 1
    raise SystemExit(_code)
