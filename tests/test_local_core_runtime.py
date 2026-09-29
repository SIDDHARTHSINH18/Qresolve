"""Tests for the local core runtime: the engine without a server or GUI.

Covers the guarantees Phase E added:
- the CLI and the solve pipeline import no HTTP/GUI stack, so the core runs
  standalone (no Electron, no desktop launcher, no port);
- verification states are derived from runs that actually happened, and an
  unjudgeable run is UNVERIFIED - never VERIFIED, never FAILED_VERIFICATION;
- availability is probed in the interpreter that would run the code, and a
  framework whose import raises anything (not just ImportError) is unavailable;
- the sandbox really bounds memory/CPU where the OS allows it, and says so
  when it cannot.

Everything runs offline. Tests needing a quantum framework skip cleanly when
that framework is absent, so the suite stays honest on a blocked environment.
"""
import importlib
import json
import os
import subprocess
import sys

import pytest

from backend.cli import main as cli_main
from backend.models import ExecutionResult
from backend.runtimes import CirqRuntime
from backend.runtimes.base import QuantumRuntime
from backend.sandbox.executor import run_python_code
from backend.sandbox.job import SandboxJob
from backend.sandbox.limits import MAX_TIMEOUT_S, SandboxLimits
from backend.validation import assess, verify_execution

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cirq's duplicate-qids bug: reproduced, deterministically fixable, verifiable.
BROKEN_CODE = (
    "import cirq\n"
    "q = cirq.LineQubit(0)\n"
    "c = cirq.Circuit(cirq.CNOT(q, q))\n"
    "print(c)\n"
)

requires_cirq = pytest.mark.skipif(
    not CirqRuntime().is_available(), reason="cirq-core not installed"
)


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "backend.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _exec(**overrides) -> ExecutionResult:
    """An ExecutionResult that looks like a run that already happened."""
    fields = {"success": True, "compiled": True, "exit_code": 0}
    fields.update(overrides)
    return ExecutionResult.model_validate(fields)


def _job_limits_work() -> bool:
    """True when this OS sets the limits, accepts assignment, and can kill.

    Each step is checked, not assumed: a job the kernel will not bind to a
    live process enforces nothing, and the sandbox must then say so.
    """
    job = SandboxJob.open(256 * 1024 * 1024, 60.0)
    if job is None:
        return False
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
    try:
        assigned = job.assign(proc.pid)
    finally:
        killed = job.kill()
        job.close()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:  # pragma: no cover - would be a bug
            proc.kill()
    return assigned and killed


# ------------------------------------------------- the core needs no server
def test_importing_the_cli_pulls_in_no_http_or_gui_stack():
    """The local entry point must stay usable without FastAPI, uvicorn or Tk."""
    code = (
        "import backend.cli, sys\n"
        "bad = sorted({m.split('.')[0] for m in sys.modules"
        " if m.split('.')[0] in {'fastapi', 'uvicorn', 'starlette', 'tkinter'}})\n"
        "print(bad)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[]", proc.stdout


def test_importing_the_solve_pipeline_pulls_in_no_http_stack():
    """`run_solve_pipeline` is the core the desktop and the CLI both consume."""
    code = (
        "import backend.api.solve, sys\n"
        "bad = sorted({m.split('.')[0] for m in sys.modules"
        " if m.split('.')[0] in {'fastapi', 'uvicorn', 'starlette', 'tkinter'}})\n"
        "print(bad)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "[]", proc.stdout


def test_cli_frameworks_json_lists_every_registered_runtime():
    rc, out, err = _run_cli(["--json", "frameworks"])
    assert rc == 0, err
    payload = json.loads(out)
    assert "interpreter" in payload
    names = {row["name"] for row in payload["runtimes"]}
    assert {"qiskit", "cirq", "pennylane", "openqasm"} <= names
    for row in payload["runtimes"]:
        assert isinstance(row["host_available"], bool)
        assert (row["host_version"] is None) is (not row["host_available"])


# ------------------------------------------------------------ CLI contract
def test_cli_rejects_bad_usage_with_exit_code_2(tmp_path):
    missing = str(tmp_path / "nope.py")
    for args in (
        ["run", missing],
        ["run", missing, "--framework", "cirq"],
        ["run", missing, "--framework", "not-a-framework"],
        ["run", missing, "--timeout", str(MAX_TIMEOUT_S + 1)],
        ["run", missing, "--timeout", "0"],
        ["serve"],
    ):
        rc, _, err = _run_cli(args)
        assert rc == 2, f"{args} -> {rc}: {err}"
        assert "qresolve:" in err


@requires_cirq
def test_cli_reports_verified_fix_with_execution_evidence(tmp_path, capsys):
    path = tmp_path / "broken.py"
    path.write_text(BROKEN_CODE, encoding="utf-8")
    rc = cli_main(["--json", "solve", str(path)])
    out = capsys.readouterr().out
    assert rc == 0, out
    payload = json.loads(out)
    assert payload["status"] == "solved"
    assert payload["verification"]["state"] == "VERIFIED"
    assert payload["verification"]["execution"]["compiled"] is True
    assert payload["attempts"][0]["verified"] is True


@requires_cirq
def test_cli_fix_command_never_claims_verification(tmp_path, capsys):
    """Proposing is not verifying: `fix` executes nothing it could certify."""
    path = tmp_path / "broken.py"
    path.write_text(BROKEN_CODE, encoding="utf-8")
    rc = cli_main(["fix", str(path)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "UNVERIFIED" in out
    assert "VERIFIED -" not in out.replace("UNVERIFIED", "")


# ------------------------------------------- truthful verification states
def test_assess_requires_both_halves_of_a_verified_fix():
    broken = _exec(success=False, compiled=True, exception_type="ValueError",
                   exception_message="Duplicate qids")
    fixed = _exec()
    state, reason = assess(fixed, original=broken)
    assert state == "VERIFIED"
    assert "reproduced" in reason and "compiled" in reason


def test_assess_never_upgrades_a_run_that_could_not_happen():
    """UNVERIFIED is the honest answer for a run the sandbox could not judge."""
    never_ran = assess(None)
    assert never_ran[0] == "UNVERIFIED"

    timed_out = assess(_exec(success=False, compiled=None, timed_out=True))
    assert timed_out[0] == "UNVERIFIED"

    harness_failed = assess(
        _exec(success=False, compiled=None, exception_type="SandboxError",
              exception_message="Execution produced no result")
    )
    assert harness_failed[0] == "UNVERIFIED"

    # A clean run proves "it executes", nothing more, when no failure was
    # reproduced first.
    alone = assess(_exec())
    assert alone[0] == "PARTIALLY_VERIFIED"
    for verdict in (never_ran, timed_out, harness_failed, alone):
        assert verdict[0] != "VERIFIED"


def test_assess_calls_a_still_broken_fix_a_failure_not_a_mystery():
    does_not_compile = assess(_exec(success=False, compiled=False, exception_type="SyntaxError"))
    assert does_not_compile[0] == "FAILED_VERIFICATION"
    assert "does not compile" in does_not_compile[1]

    still_fails = assess(_exec(success=False, compiled=True, exception_type="ValueError",
                               exception_message="bad"))
    assert still_fails[0] == "FAILED_VERIFICATION"
    assert "still fails" in still_fails[1]


def test_verify_execution_keeps_verified_flag_and_state_in_agreement():
    verdict = verify_execution(_exec(success=False, compiled=None, timed_out=True))
    assert verdict.verified is False
    assert verdict.state == "UNVERIFIED"
    assert verdict.reason == verdict.notes

    verdict = verify_execution(_exec(), original=_exec(success=False, compiled=True))
    assert verdict.verified is True
    assert verdict.state == "VERIFIED"


# ------------------------------------------------- runtime contract changes
class _StubRuntime(QuantumRuntime):
    name = "stub"

    def execute(self, code, limits=None):  # pragma: no cover - never called
        raise NotImplementedError


def test_availability_probe_treats_any_import_failure_as_unavailable():
    """A framework blocked mid-import by an application-control policy raises
    something other than ImportError and must not be reported as working."""

    class BoomFinder:
        def find_spec(self, name, path=None, target=None):
            if name == "qresolve_stub_half_broken":
                raise TypeError("partially initialised module")
            return None

    runtime = _StubRuntime()
    runtime.probe_imports = ("qresolve_stub_half_broken",)
    finder = BoomFinder()
    sys.meta_path.insert(0, finder)
    try:
        importlib.invalidate_caches()
        assert runtime.import_probe() == (False, None)
        assert runtime.is_available() is False
        assert runtime.version() is None
    finally:
        sys.meta_path.remove(finder)
        importlib.invalidate_caches()


def test_availability_probe_reads_version_of_an_installed_module():
    runtime = _StubRuntime()
    runtime.probe_imports = ("json",)
    runtime.version_module = "json"
    available, version = runtime.import_probe()
    assert available is True
    assert version == json.__version__


def test_missing_framework_is_unavailable_not_an_error():
    runtime = _StubRuntime()
    runtime.probe_imports = ("qresolve_module_that_does_not_exist",)
    assert runtime.is_available() is False


# ------------------------------------------------------------ sandbox limits
def test_limits_are_validated_before_any_run():
    for kwargs in (
        {"timeout_s": 0},
        {"timeout_s": MAX_TIMEOUT_S + 1},
        {"max_output_bytes": 0},
        {"max_memory_mb": 0},
        {"max_cpu_s": 0},
    ):
        with pytest.raises(ValueError):
            SandboxLimits(**kwargs)
    assert SandboxLimits(timeout_s=10).cpu_limit_s > 10
    assert SandboxLimits(timeout_s=10, max_cpu_s=3).cpu_limit_s == 3
    assert SandboxLimits(max_memory_mb=512).max_memory_bytes == 512 * 1024 * 1024


@requires_cirq
def test_sandbox_runs_print_utf8_circuit_art_without_failing():
    """Isolated mode ignores PYTHONIOENCODING, so the interpreter flag does it."""
    code = (
        "import cirq\n"
        "q0, q1 = cirq.LineQubit.range(2)\n"
        "print(cirq.Circuit(cirq.H(q0), cirq.CNOT(q0, q1)))\n"
    )
    result = run_python_code(code)
    assert result.success, result.stderr
    assert "\u2500\u2500\u2500H\u2500\u2500\u2500" in result.stdout


def test_memory_limit_is_enforced_or_honestly_reported():
    bomb = "data = [bytearray(64 * 1024 * 1024) for _ in range(40)]\nprint('done')\n"
    result = run_python_code(bomb, limits=SandboxLimits(max_memory_mb=128, timeout_s=90))
    if _job_limits_work():
        assert not result.success
        assert "MemoryError" in result.stderr
        assert "NOT enforced" not in result.stderr
    else:
        assert "NOT enforced" in result.stderr


@pytest.mark.skipif(not _job_limits_work(), reason="this Windows session refuses job objects")
def test_cpu_time_limit_stops_a_burner_and_says_so():
    burner = "i = 0\nwhile True:\n    i += 1\n"
    result = run_python_code(burner, limits=SandboxLimits(timeout_s=90, max_cpu_s=2.0))
    assert not result.success
    assert result.timed_out is False  # the kernel stopped it, not the watchdog
    assert "CPU time reached" in result.stderr
    assert result.execution_time_ms is not None and result.execution_time_ms < 60_000
