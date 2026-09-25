"""Subprocess sandbox executor.

Runs Python code in a fresh interpreter process with:
- an isolated temp working directory (deleted afterwards)
- a scrubbed environment (no application secrets, no PYTHON*/env injection)
- CPython isolated mode (`-I`: ignores env vars and user site-packages)
- hard timeout and output truncation
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

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
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _interpreter() -> str:
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
    try:
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            env=_clean_env(),
            capture_output=True,
            timeout=limits.timeout_s,
        )
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
        success = exit_code == 0
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        stderr += b"\n[Sandbox] Execution timed out after %.1fs" % limits.timeout_s
        success = False

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
            [_interpreter(), "-I", script_name],
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
        shutil.rmtree(workdir, ignore_errors=True)


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

        result = _run_cmd([_interpreter(), "-I", entry], workdir, limits)
        result.workdir = workdir
        for name in collect_files or []:
            path = os.path.join(workdir, name)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    result.files[name] = f.read()
        return result
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
