"""Tests for the desktop packaging support: port/interpreter policy invariants.

The packaged app pins the sandbox interpreter via QRESOLVE_SANDBOX_PYTHON
(frozen builds) — these tests lock in that the mechanism cannot leak into
executed user code and cannot be hijacked by a nonexistent path.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.sandbox.executor import (
    _ACTIVE_CHILDREN,
    _ENV_ALLOWLIST,
    _interpreter,
    terminate_active_children,
)


def test_no_qresolve_variables_reach_the_sandbox_environment():
    assert not [k for k in _ENV_ALLOWLIST if k.startswith("QRESOLVE")]


def test_interpreter_defaults_to_current_python(monkeypatch):
    monkeypatch.delenv("QRESOLVE_SANDBOX_PYTHON", raising=False)
    assert _interpreter() == sys.executable


def test_pinned_interpreter_is_used_only_when_it_exists(monkeypatch, tmp_path):
    real = sys.executable
    monkeypatch.setenv("QRESOLVE_SANDBOX_PYTHON", real)
    assert _interpreter() == real
    monkeypatch.setenv("QRESOLVE_SANDBOX_PYTHON", str(tmp_path / "nope" / "python.exe"))
    assert _interpreter() == sys.executable  # stale pin must not break execution


def test_frontend_is_served_same_origin_by_design():
    """The desktop app mounts the built UI on the API port; the frontend API
    layer uses same-origin relative paths, so no host is hard-wired."""
    src = Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "qresolve.js"
    text = src.read_text(encoding="utf-8")
    assert "8000" not in text and "localhost" not in text


# --- M6: windowed packaging contract -----------------------------------------

ROOT = Path(__file__).resolve().parents[1]


def test_pyinstaller_spec_builds_a_windowed_app():
    """M6 §1: console=False — a CMD window must never exist at all."""
    text = (ROOT / "QResolve.spec").read_text(encoding="utf-8")
    assert "console=False" in text
    assert "console=True" not in text


def test_sandbox_children_launch_without_console_windows():
    """A GUI-subsystem parent flashing a console per sandbox run would defeat §1."""
    if os.name != "nt":
        pytest.skip("Windows-only console suppression flag")
    from backend.sandbox import executor

    assert executor._NO_WINDOW == subprocess.CREATE_NO_WINDOW


def test_terminate_active_children_only_touches_owned_processes():
    class FakeProc:
        def __init__(self, alive=True):
            self._alive = alive
            self.terminated = False
            self.killed = False

        def poll(self):
            return None if self._alive else 0

        def terminate(self):
            self.terminated = True
            self._alive = False

        def wait(self, timeout=None):
            return 0

        def kill(self):
            self.killed = True

    a, b = FakeProc(), FakeProc()
    _ACTIVE_CHILDREN.update({a, b})
    assert terminate_active_children() == 2
    assert a.terminated and b.terminated
    assert not _ACTIVE_CHILDREN


def test_terminate_active_children_forces_only_when_terminate_fails():
    class _Stubborn:
        def __init__(self):
            self.terminated = False
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired(cmd="x", timeout=0)
            return 0

        def kill(self):
            self.killed = True

    s = _Stubborn()
    _ACTIVE_CHILDREN.add(s)
    terminate_active_children()
    assert s.terminated and s.killed
    assert not _ACTIVE_CHILDREN


def test_launcher_phase_order_matches_the_startup_state_machine():
    import desktop.qresolve_desktop as d

    assert d.PHASES == (
        "STARTING", "CHECK PORT", "PORT AVAILABLE", "START BACKEND",
        "WAIT FOR HEALTH", "HEALTHY", "OPEN UI", "RUNNING",
    )


def test_port_conflict_path_reports_the_spec_error(monkeypatch):
    """M6 §4: GUI error 'QResolve could not start' + close-the-app guidance."""
    import backend.ports as ports
    import desktop.qresolve_desktop as d

    def _boom(port, host=ports.BACKEND_HOST):
        raise ports.PortConflictError(
            f"Port {port} is already being used by another application.\n"
            "Close the application using this port and try again.\n"
            "QResolve never switches ports silently."
        )

    monkeypatch.setattr(ports, "ensure_port_free", _boom)
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(d, "_show_dialog", lambda t, m: shown.append((t, m)))
    assert d.main() == 1
    assert shown == [(
        "QResolve could not start",
        "Port 8321 is already being used by another application.\n"
        "Close the application using this port and try again.\n"
        "QResolve never switches ports silently.",
    )]


# --- M7: installed-application contract --------------------------------------

def test_startup_crash_log_goes_to_the_per_user_location(monkeypatch, tmp_path):
    """M7 §6: an installed app lives in a protected directory, so the one file
    the launcher writes must resolve under the per-user app-data root."""
    import desktop.qresolve_desktop as d

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert d._crash_log_path() == str(
        tmp_path / "QResolve" / "QResolve-startup-error.log"
    )


def test_nothing_is_written_next_to_the_executable():
    """Reads may resolve beside the exe (locating `_python`); writes may not."""
    text = (ROOT / "desktop" / "qresolve_desktop.py").read_text(encoding="utf-8")
    before_helper = text.split("def _crash_log_path")[0]
    assert "QResolve-startup-error.log" not in before_helper
    assert "QResolve-startup-error.log" in text.split("def _crash_log_path")[1]


# --- M7: installer contract ---------------------------------------------------

def test_installer_is_update_ready_and_free_of_developer_paths():
    """M7 §5/§10: a fixed AppId makes the next Setup.exe an in-place upgrade,
    and nothing may pin the application to the machine that built it."""
    import re

    iss = (ROOT / "installer" / "QResolve.iss").read_text(encoding="utf-8")
    # Inno escapes a literal "{" as "{{"; the closing brace stays single.
    assert re.search(r"^AppId=\{\{[0-9A-Fa-f-]{36}\}$", iss, re.MULTILINE)
    assert "DefaultDirName={autopf}\\{#MyAppName}" in iss
    assert '"{autoprograms}\\{#MyAppName}"' in iss
    assert '"{autodesktop}\\{#MyAppName}"' in iss
    assert "UninstallDisplayIcon={app}\\{#MyAppExeName}" in iss
    assert "C:\\Users\\" not in iss and "Downloads" not in iss


def test_installer_ships_the_exe_its_ui_bundle_and_its_interpreter():
    iss = (ROOT / "installer" / "QResolve.iss").read_text(encoding="utf-8")
    for needed in ("_internal\\*", "_python\\*", "QResolve.exe"):
        assert needed in iss, f"{needed} would not be installed"


def test_installer_keeps_the_pyi_and_interpreter_directories_nested():
    """A tree wildcard must not land directly in {app}.

    Inno flattens the *contents* of a wildcard Source into DestDir, so
    "src\\_internal\\* -> {app}" would drop base_library.zip, web\\ and
    _tkinter.pyd next to QResolve.exe - and collide with the same filenames
    coming from _python. PyInstaller only finds its payload in _internal.
    """
    import re

    iss = (ROOT / "installer" / "QResolve.iss").read_text(encoding="utf-8")
    files = iss.split("[Files]")[1].split("\n[")[0]
    for source, dest in re.findall(
        r'^Source:\s*"([^"]+)"\s*;\s*DestDir:\s*"([^"]+)"', files, re.MULTILINE
    ):
        if source.endswith("\\*"):
            tail = source.rsplit("\\", 2)[-2]
            assert dest == f"{{app}}\\{tail}", f"{source} would be flattened into {dest}"


def test_installer_prunes_the_managed_trees_before_copying():
    """Updates must not leave the previous build's modules behind.

    A frozen payload is replaced as a whole; stale files in _internal or _python
    would be imported instead of the new ones.
    """
    iss = (ROOT / "installer" / "QResolve.iss").read_text(encoding="utf-8")
    prune = iss.split("[InstallDelete]")[1].split("\n[")[0]
    for tree in ("{app}\\_internal", "{app}\\_python"):
        assert f'Type: filesandordirs; Name: "{tree}"' in prune, f"{tree} is not pruned"


def test_shipped_interpreter_carries_no_bytecode_caches():
    """A .pyc embeds the absolute path it was built from.

    Shipping them would publish the developer's directory layout inside the
    installed application, so they are stripped from the packaged interpreter.
    """
    interpreter = ROOT / "build_package" / "_python"
    assert interpreter.is_dir(), "embedded interpreter not packaged yet"
    stale = [p for p in interpreter.rglob("*.pyc")]
    assert not stale, f"{len(stale)} compiled files would leak their build paths"


def test_sandbox_child_never_writes_bytecode():
    """Only the -B flag stops .pyc output: -I mode ignores PYTHON* variables.

    Without it a packaged run caches bytecode beside its own modules, i.e.
    inside the installation directory - which is read-only in Program Files, and
    would publish the developer's paths either way.
    """
    from backend.sandbox.executor import SandboxLimits, run_python_code

    result = run_python_code(
        "import sys\nprint('DONT_WRITE_BYTECODE=' + str(sys.dont_write_bytecode))\n",
        limits=SandboxLimits(timeout_s=30),
    )
    assert result.success, result.stderr
    assert "DONT_WRITE_BYTECODE=True" in result.stdout


def test_sandbox_workdir_is_gone_after_a_run():
    import os

    from backend.sandbox.executor import SandboxLimits, run_python_code

    result = run_python_code("print('ok')\n", limits=SandboxLimits(timeout_s=30))
    assert result.success, result.stderr
    assert result.workdir
    assert not os.path.isdir(result.workdir), f"{result.workdir} survived the run"


def test_installer_version_tracks_the_application_version():
    import re

    from backend.main import app

    iss = (ROOT / "installer" / "QResolve.iss").read_text(encoding="utf-8")
    declared = re.search(r'#define MyAppVersion "([^"]+)"', iss).group(1)
    assert declared == app.version


def test_version_resource_matches_the_application_version():
    from backend.main import app

    txt = (ROOT / "installer" / "version_info.txt").read_text(encoding="utf-8")
    parts = tuple(int(n) for n in app.version.split(".")) + (0,)
    assert f"filevers={parts}" in txt
    assert f"prodvers={parts}" in txt
    assert f"'FileVersion', '{app.version}'" in txt
    assert f"'ProductVersion', '{app.version}'" in txt


# --- the control window is a passive status display ---------------------------
#
# The browser is opened by _readiness() as soon as the backend is healthy, so a
# second "Open interface" affordance only invites the user to launch duplicate
# tabs. The window stays for one reason: closing it is how QResolve quits.
# Nothing here opens a Tk display - _run_gui is driven through a stub module.

LAUNCHER = ROOT / "desktop" / "qresolve_desktop.py"


def _launcher_functions():
    import ast

    tree = ast.parse(LAUNCHER.read_text(encoding="utf-8"))
    return {
        n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


class _StubWidget:
    """Records construction; every Tk method the launcher touches is inert."""

    def __init__(self, built: list[str], kind: str):
        self._built = built
        self.kind = kind
        built.append(kind)

    def pack(self, *args, **kwargs) -> None:
        return None


class _StubRoot(_StubWidget):
    def __init__(self, built, protocols, destroyed, pump_budget=8):
        super().__init__(built, "Tk")
        self._protocols = protocols
        self._destroyed = destroyed
        self._budget = pump_budget

    def title(self, text) -> None:
        return None

    def geometry(self, spec) -> None:
        return None

    def resizable(self, *args) -> None:
        return None

    def protocol(self, name, handler) -> None:
        self._protocols[name] = handler

    def after(self, delay_ms, callback=None):
        # No event loop exists here, so run the callback inline a bounded number
        # of times: enough to drain the queue, never enough to spin forever.
        if callback is not None and self._budget > 0:
            self._budget -= 1
            callback()

    def destroy(self) -> None:
        self._destroyed.append(True)

    def mainloop(self) -> None:
        return None


class _StubVar:
    def __init__(self, values, value=None):
        self._values = values
        values.append(value)

    def set(self, value) -> None:
        self._values.append(value)


def _drive_run_gui(monkeypatch, events, base="http://127.0.0.1:8321"):
    """Run _run_gui against a stub tkinter and report what it built."""
    import queue
    import types

    import desktop.qresolve_desktop as d

    built: list[str] = []
    protocols: dict = {}
    destroyed: list[bool] = []
    statuses: list[str] = []
    dialogs: list[tuple[str, str]] = []
    shutdowns: list[int] = []

    stub = types.ModuleType("tkinter")
    stub.Tk = lambda: _StubRoot(built, protocols, destroyed)
    stub.StringVar = lambda value=None: _StubVar(statuses, value)
    stub.Label = lambda *a, **k: _StubWidget(built, "Label")
    stub.Frame = lambda *a, **k: _StubWidget(built, "Frame")
    stub.Button = lambda *a, **k: _StubWidget(built, "Button")
    stub.messagebox = types.SimpleNamespace(
        showerror=lambda title, message: dialogs.append((title, message))
    )
    monkeypatch.setitem(sys.modules, "tkinter", stub)
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", stub.messagebox)

    exit_code = d._run_gui(events, base, lambda: shutdowns.append(1))
    return {
        "exit_code": exit_code,
        "built": built,
        "protocols": protocols,
        "destroyed": destroyed,
        "statuses": statuses,
        "dialogs": dialogs,
        "shutdowns": shutdowns,
    }


def test_control_window_builds_no_buttons(monkeypatch):
    import queue

    run = _drive_run_gui(monkeypatch, queue.Queue())
    assert run["built"] == ["Tk", "Label", "Label"]
    assert "Button" not in run["built"] and "Frame" not in run["built"]


def test_control_window_has_no_button_in_its_source():
    """Guards the same contract statically, so a rebuilt widget cannot slip in
    through a code path the stub driver does not reach."""
    import ast

    source = ast.unparse(_launcher_functions()["_run_gui"])
    assert "Button" not in source
    assert "Open interface" not in source
    assert ".pack(" in source and "textvariable=status" in source  # status label remains


def test_running_phase_reports_the_url_and_how_to_quit(monkeypatch):
    import queue

    events = queue.Queue()
    events.put(("phase", "WAIT FOR HEALTH"))
    events.put(("phase", "RUNNING"))
    run = _drive_run_gui(monkeypatch, events, base="http://127.0.0.1:8321")
    assert run["exit_code"] == 0
    assert run["statuses"][-1] == (
        "Running at http://127.0.0.1:8321\nClose this window to quit QResolve."
    )
    assert run["shutdowns"] == [1]  # the backend is stopped when the window closes


def test_closing_the_control_window_destroys_it(monkeypatch):
    """WM_DELETE_WINDOW is the only quit affordance left, so it must be wired."""
    import queue

    run = _drive_run_gui(monkeypatch, queue.Queue())
    assert list(run["protocols"]) == ["WM_DELETE_WINDOW"]
    run["protocols"]["WM_DELETE_WINDOW"]()
    assert run["destroyed"] == [True]


def test_the_browser_is_opened_once_by_the_readiness_probe():
    """Auto-opening the UI must survive the button removal, and must stay in the
    one place that knows the backend answered /health."""
    import ast

    tree = ast.parse(LAUNCHER.read_text(encoding="utf-8"))
    opens = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "open"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "webbrowser"
    ]
    assert len(opens) == 1, "the UI must be opened exactly once"

    readiness = _nested_function(tree, "_readiness")
    assert readiness.lineno <= opens[0].lineno <= readiness.end_lineno
    assert "webbrowser" not in ast.unparse(_launcher_functions()["_run_gui"])


def _nested_function(tree, name: str):
    """Fetch a function defined inside another function (e.g. main._readiness)."""
    import ast

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")
