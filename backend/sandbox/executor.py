"""Subprocess sandbox executor.

Runs Python code in a fresh interpreter process with:
- an isolated temp working directory (deleted afterwards)
- a scrubbed environment (no application secrets, no PYTHON*/env injection)
- CPython isolated mode (`-I`: ignores env vars and user site-packages) plus `-B`:
  no bytecode cache is ever written, not even into the packaged interpreter
- `-X utf8`, because isolated mode also ignores PYTHONIOENCODING and circuit
  diagrams printed by user code are not ASCII
- hard timeout and output truncation
- on Windows, a kernel job object that caps committed memory and per-process
  CPU time and kills the whole child tree (see backend/sandbox/job.py)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

from backend.sandbox.job import SandboxJob, limit_report
from backend.sandbox.limits import SandboxLimits

# Env vars the child is allowed to see. Everything else (API keys, tokens,
# anything the FastAPI process holds) is dropped.
_ENV_ALLOWLIST = [
    "PATH",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "WINDIR",
    "TEMP",
    "TMP",
    "SYSTEMDRIVE",
    "HOMEDRIVE",
    "HOMEPATH",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "COMMONPROGRAMFILES",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
]

# The windowed desktop exe must never flash a console when it runs a sandbox
# child or any helper executable.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# Popen handles of sandbox children started by THIS process. Shutdown code may
# only ever touch children listed here — never a name-based taskkill.
_ACTIVE_CHILDREN: set[subprocess.Popen] = set()


def _reap(proc: subprocess.Popen) -> None:
    """terminate -> wait -> force only if it refuses to stop (owned child only)."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def terminate_active_children() -> int:
    """Stop every sandbox child this process still owns. Returns how many.

    Used by the desktop launcher before exiting so a windowed QResolve never
    orphans an interpreter running user quantum code on a closed port.
    """
    children = list(_ACTIVE_CHILDREN)
    _ACTIVE_CHILDREN.clear()
    for proc in children:
        _reap(proc)
    return len(children)


@dataclass
class SandboxResult:
    success: bool = False
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    output_truncated: bool = False
    execution_time_ms: float | None = None
    workdir: str | None = None
    files: dict[str, str] = field(default_factory=dict)

    def read_file(self, name: str) -> str | None:
        return self.files.get(name)


def _clean_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    # -I mode ignores every PYTHON* variable, so the child's text encoding is
    # set by the -X utf8 command-line flag instead of PYTHONIOENCODING here;
    # without that flag a circuit diagram printed by user code aborts with
    # UnicodeEncodeError on a cp1252 console. -B keeps the intent explicit:
    # no bytecode cache is written.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


# Command-line interpreter options shared by every sandbox run.
_INTERPRETER_FLAGS = ["-I", "-B", "-X", "utf8"]


def _drop_workdir(workdir: str) -> None:
    """Remove the temp dir, retrying while a killed child still holds it.

    A sandbox process keeps the workdir as its cwd, so on Windows the last rmtree
    of a run that was terminated during shutdown can fail on the directory alone
    and leave an empty folder behind.
    """
    for _ in range(10):
        shutil.rmtree(workdir, ignore_errors=True)
        if not os.path.isdir(workdir):
            return
        time.sleep(0.2)


def sandbox_interpreter() -> str:
    """Python used to run sandboxed code.

    In a frozen desktop build, sys.executable is the app binary itself, so the
    launcher pins a bundled interpreter via QRESOLVE_SANDBOX_PYTHON. That
    variable is read in the server process only and is deliberately absent
    from _ENV_ALLOWLIST, so executed user code can never see or set it.
    """
    pinned = os.environ.get("QRESOLVE_SANDBOX_PYTHON", "")
    if pinned and os.path.isfile(pinned):
        return pinned
    return sys.executable


def _run_cmd(
    cmd: list[str],
    workdir: str,
    limits: SandboxLimits,
) -> SandboxResult:
    started = time.perf_counter()
    timed_out = False
    notes: list[str] = []
    # Bounds memory/CPU in kernel and ties the whole child tree to this
    # process; None means this platform or session refused, which is reported
    # rather than assumed away.
    job = SandboxJob.open(limits.max_memory_bytes, limits.cpu_limit_s)
    proc = subprocess.Popen(
        cmd,
        cwd=workdir,
        env=_clean_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_NO_WINDOW,
    )
    _ACTIVE_CHILDREN.add(proc)
    try:
        if job is not None and not job.assign(proc.pid):
            notes.append(
                "[Sandbox] Memory and CPU limits were NOT enforced: this Windows "
                "session refused a job object for the child."
            )
        try:
            stdout, stderr = proc.communicate(timeout=limits.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _reap(proc)
            if job is not None:
                job.kill()  # anything the child spawned dies with it
            stdout, stderr = proc.communicate()
            stderr = (stderr or b"") + b"\n[Sandbox] Execution timed out after %.1fs" % limits.timeout_s
        exit_code = None if timed_out else proc.returncode
        success = exit_code == 0
        if job is not None and not success and not timed_out:
            stopped = limit_report(job, exit_code)
            if stopped:
                notes.append(f"[Sandbox] {stopped}")
    finally:
        _ACTIVE_CHILDREN.discard(proc)
        if job is not None:
            job.close()

    elapsed_ms = (time.perf_counter() - started) * 1000.0

    truncated = False
    out_text = stdout.decode("utf-8", errors="replace")
    err_text = stderr.decode("utf-8", errors="replace")
    if len(out_text) > limits.max_output_bytes:
        out_text = out_text[: limits.max_output_bytes]
        truncated = True
    if len(err_text) > limits.max_output_bytes:
        err_text = err_text[: limits.max_output_bytes]
        truncated = True
    # Appended after truncation so the sandbox's own statement always survives.
    for note in notes:
        err_text = f"{err_text}\n{note}" if err_text.strip() else note

    return SandboxResult(
        success=success,
        exit_code=exit_code,
        stdout=out_text,
        stderr=err_text,
        timed_out=timed_out,
        output_truncated=truncated,
        execution_time_ms=elapsed_ms,
    )


def run_python_code(
    code: str,
    limits: SandboxLimits | None = None,
    script_name: str = "user_code.py",
    collect_files: list[str] | None = None,
) -> SandboxResult:
    """Execute `code` as a standalone script in a sandboxed subprocess.

    `collect_files` names files in the working dir to read back before the
    temp directory is removed (used by runtimes for structured results).
    """
    limits = limits or SandboxLimits()
    workdir = tempfile.mkdtemp(prefix="qresolve-sandbox-")
    try:
        script_path = os.path.join(workdir, script_name)
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        result = _run_cmd(
            [sandbox_interpreter(), *_INTERPRETER_FLAGS, script_name],
            workdir,
            limits,
        )
        result.workdir = workdir
        for name in collect_files or []:
            path = os.path.join(workdir, name)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    result.files[name] = f.read()
        return result
    finally:
        _drop_workdir(workdir)


def run_files(
    files: dict[str, str],
    entry: str,
    limits: SandboxLimits | None = None,
    collect_files: list[str] | None = None,
) -> SandboxResult:
    """Write several files into a temp dir and execute `entry` among them."""
    limits = limits or SandboxLimits()
    workdir = tempfile.mkdtemp(prefix="qresolve-sandbox-")
    try:
        for name, content in files.items():
            path = os.path.join(workdir, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

        result = _run_cmd([sandbox_interpreter(), *_INTERPRETER_FLAGS, entry], workdir, limits)
        result.workdir = workdir
        for name in collect_files or []:
            path = os.path.join(workdir, name)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    result.files[name] = f.read()
        return result
    finally:
        _drop_workdir(workdir)
