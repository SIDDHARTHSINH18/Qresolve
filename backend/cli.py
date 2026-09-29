"""QResolve local core runtime — the debugging engine without a server or GUI.

    python -m backend.cli solve broken.py --framework cirq

This is a client of exactly the same pipeline the HTTP API calls
(backend/api/solve.py); no debugging logic lives here. Importing this module
never pulls in FastAPI, uvicorn, tkinter or a port, so the core engine works
standalone: analyze -> diagnose -> fix -> execute -> verify -> report evidence.

Exit codes: 0 = the command did what it claims (code ran cleanly, a fix was
verified, or a proposal was produced); 1 = not verified / no fix / a failure
was reproduced; 2 = bad usage or unreadable input; 130 = interrupted.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass

MARK = {"VERIFIED": "+", "PARTIALLY_VERIFIED": "~", "FAILED_VERIFICATION": "!", "UNVERIFIED": "?"}


@dataclass
class CliError(Exception):
    message: str


def _read_source(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise CliError(f"Cannot read {path}: {exc}") from exc


def _runtime_for(code: str, framework: str | None):
    from backend.analyzer import detect_framework
    from backend.runtimes import get_runtime

    if framework:
        runtime = get_runtime(framework)
        if runtime is None:
            raise CliError(f"No runtime registered for framework: {framework}")
        return framework, runtime
    detected, _, _ = detect_framework(code)
    runtime = get_runtime(detected) if detected else None
    if runtime is None:
        raise CliError(
            f"Could not detect a runnable framework ({detected or 'none'}); "
            "pass --framework explicitly."
        )
    return detected, runtime


def _limits(timeout_s: float | None):
    if timeout_s is None:
        return None
    from backend.sandbox.limits import MAX_TIMEOUT_S, SandboxLimits

    if timeout_s <= 0 or timeout_s > MAX_TIMEOUT_S:
        raise CliError(
            f"--timeout must be greater than 0 and at most {MAX_TIMEOUT_S:g} seconds "
            "(the sandbox's hard ceiling)."
        )
    return SandboxLimits(timeout_s=timeout_s)


def _first_line(text: str | None) -> str:
    for line in reversed((text or "").strip().splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _configure_streams() -> None:
    """Report quantum-codepoint output (cirq's ASCII art, e.g.) reliably.

    A Windows pipe defaults to cp1252, which cannot encode box-drawing
    characters that appear in the very program output this tool must show as
    evidence; that raised UnicodeEncodeError and lost the report.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (OSError, ValueError):
            pass


# ----------------------------------------------------------------- commands
def cmd_frameworks(args) -> int:
    from backend.runtimes import all_runtimes
    from backend.sandbox.executor import sandbox_interpreter

    rows = []
    for name, runtime in sorted(all_runtimes().items()):
        row = {"name": name, "host_available": runtime.is_available(), "host_version": runtime.version()}
        if args.probe:
            probe = runtime.sandbox_probe()
            row["sandbox_available"] = probe["available"]
            row["sandbox_version"] = probe["version"]
            row["sandbox_error"] = probe["error"]
        rows.append(row)

    if args.json:
        print(json.dumps({"interpreter": sandbox_interpreter(), "runtimes": rows}, indent=2))
        return 0

    print(f"sandbox interpreter : {sandbox_interpreter()}")
    print(f"{'framework':<12} {'here':<8} version")
    for row in rows:
        available = "yes" if row["host_available"] else "NO"
        print(f"{row['name']:<12} {available:<8} {row['host_version'] or '-'}")
        if args.probe:
            in_sandbox = "yes" if row.get("sandbox_available") else "NO"
            detail = row.get("sandbox_version") or row.get("sandbox_error") or "-"
            print(f"{'':<12} in sandbox={in_sandbox} {detail}")
    if not args.probe:
        print("\n(--probe re-checks each framework inside the interpreter that runs code)")
    return 0


def cmd_run(args) -> int:
    code = _read_source(args.path)
    name, runtime = _runtime_for(code, args.framework)
    execution = runtime.execute(code, limits=_limits(args.timeout))

    if args.json:
        print(execution.model_dump_json(indent=2))
        return 0 if execution.success else 1

    print(f"framework   : {name}")
    print(f"compiled    : {_yes_no(execution.compiled)}")
    print(f"success     : {_yes_no(execution.success)}")
    print(f"exit code   : {execution.exit_code}")
    print(f"timed out   : {_yes_no(execution.timed_out)}")
    print(f"duration    : {_ms(execution.execution_time_ms)}")
    if execution.stdout.strip():
        print("stdout      :\n" + _indent(execution.stdout))
    if not execution.success:
        print(f"error       : {execution.exception_type}: {execution.exception_message}")
        if execution.traceback_text:
            print("traceback   : " + _first_line(execution.traceback_text))
    return 0 if execution.success else 1


def cmd_diagnose(args) -> int:
    from backend.analyzer import error_from_execution
    from backend.diagnostics import classify

    code = _read_source(args.path)
    name, runtime = _runtime_for(code, args.framework)
    execution = runtime.execute(code, limits=_limits(args.timeout))
    error = error_from_execution(execution, code)
    if error is None:
        print(f"{name}: executed cleanly, nothing to diagnose ({_ms(execution.execution_time_ms)})")
        return 0

    diagnosis = classify(error)
    if args.json:
        print(diagnosis.model_dump_json(indent=2))
        return 1
    print(f"framework   : {name}")
    print(f"reproduced  : {error.exception_type} at line {error.line_number}: {error.message}")
    print(f"category    : {diagnosis.category}")
    print(f"diagnosis   : {diagnosis.summary}")
    for hypothesis in diagnosis.hypotheses:
        print(f"  cause     : {hypothesis.cause}")
        print(f"  try       : {hypothesis.suggestion}")
    return 1


def cmd_fix(args) -> int:
    from backend.api.solve import run_fix
    from backend.models import FixRequest

    code = _read_source(args.path)
    response = run_fix(FixRequest(code=code, error=None, diagnosis=None))
    if args.json:
        print(response.model_dump_json(indent=2))
        return 0 if response.fix else 1

    print(f"status      : {response.status}")
    if response.detail:
        print(f"detail      : {response.detail}")
    if response.diagnosis:
        print(f"category    : {response.diagnosis.category}")
    if response.fix:
        print(f"strategy    : {response.fix.strategy}")
        print(f"change      : {response.fix.description}")
        print("diff        :\n" + _indent(response.fix.diff))
        print("verdict     : UNVERIFIED - this command only proposes; nothing was executed.")
        return 0
    return 1


def cmd_validate(args) -> int:
    from backend.validation import verify_execution

    code = _read_source(args.path)
    name, runtime = _runtime_for(code, args.framework)
    verdict = verify_execution(runtime.execute(code, limits=_limits(args.timeout)))
    if args.json:
        print(verdict.model_dump_json(indent=2))
        return 0 if verdict.verified else 1
    print(f"framework   : {name}")
    print(f"executed    : {_yes_no(verdict.execution.success)} ({_ms(verdict.execution.execution_time_ms)})")
    print(f"verdict     : {verdict.state}")
    print(f"evidence    : {verdict.reason}")
    return 0 if verdict.verified else 1


def _preflight(code: str, args) -> None:
    """Fail on a bad --timeout/--framework before anything is executed.

    The pipeline itself raises LookupError for an unknown framework; a CLI
    user should get one clear line, not a traceback from the engine.
    """
    _limits(args.timeout)
    if args.framework:
        _runtime_for(code, args.framework)


def cmd_solve(args) -> int:
    from backend.api.solve import run_solve_pipeline
    from backend.models import SolveRequest

    code = _read_source(args.path)
    _preflight(code, args)
    request = SolveRequest(code=code, framework=args.framework, timeout_seconds=args.timeout)
    response = run_solve_pipeline(request)

    if args.json:
        print(response.model_dump_json(indent=2))
        return 0 if response.status in {"solved", "no_error"} else 1

    print(f"file        : {args.path}")
    print(f"framework   : {response.framework.framework or 'undetected'}")
    print(f"status      : {response.status}")

    original = response.execution
    if original is not None:
        outcome = "ran cleanly" if original.success else _first_line(
            f"{original.exception_type}: {original.exception_message}"
        )
        print(f"1 REPRODUCE : {'-' if original.success else 'X'} {outcome}")
    if response.error:
        print(f"2 DIAGNOSE  : {response.diagnosis.category} - {response.diagnosis.summary}")
        print(f"              at {response.error.exception_type} line {response.error.line_number}")
    elif response.diagnosis:
        print(f"2 DIAGNOSE  : {response.diagnosis.summary}")
    if response.detail:
        print(f"              {response.detail}")
    if response.fix:
        print(f"3 FIX       : {response.fix.strategy} - {response.fix.description}")
        print("              " + _indent(response.fix.diff, 14).strip("\n").replace("\n", "\n              "))
    verdict = response.verification
    if verdict is not None:
        print(f"4 EXECUTE   : compiled={_yes_no(verdict.execution.compiled)} "
              f"success={_yes_no(verdict.execution.success)} "
              f"({_ms(verdict.execution.execution_time_ms)})")
        print(f"5 VERIFY    : {MARK.get(verdict.state, ' ')} {verdict.state} - {verdict.reason}")
    elif response.fix is not None:
        print("5 VERIFY    : ? UNVERIFIED - a fix exists but was never executed.")

    if response.attempts:
        print("ATTEMPTS    :")
        for attempt in response.attempts:
            state = "VERIFIED" if attempt.verified else (
                "UNVERIFIED" if attempt.execution is None else "FAILED_VERIFICATION"
            )
            print(f"  #{attempt.attempt} {attempt.source} level {attempt.level} -> {state}")
            if attempt.why_failed:
                print(f"      why: {attempt.why_failed}")

    if verdict is not None and verdict.state == "VERIFIED":
        print("\nEVIDENCE    :")
        for line in verdict.execution.stdout.strip().splitlines()[:6]:
            print(f"      {line}")
    return 0 if response.status in {"solved", "no_error"} else 1


def _yes_no(value) -> str:
    return {True: "yes", False: "no", None: "unknown"}[value]


def _ms(value) -> str:
    return f"{value:.0f} ms" if isinstance(value, (int, float)) else "n/a"


def _indent(text: str, width: int = 4) -> str:
    pad = " " * width
    return "\n".join(pad + line for line in (text or "").rstrip().splitlines())


# --------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.cli",
        description="QResolve local core runtime: debug quantum code without the desktop app.",
        epilog="UNDERSTAND -> DIAGNOSE -> FIX -> EXECUTE -> VERIFY -> REPORT EVIDENCE",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--python",
        dest="sandbox_python",
        help="interpreter used to execute user code (defaults to this one, or QRESOLVE_SANDBOX_PYTHON)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(
        name: str, help_text: str, needs_framework: bool = True, needs_timeout: bool = True
    ):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("path", help="source file to debug, or '-' for stdin")
        if needs_framework:
            sp.add_argument("--framework", help="qiskit | cirq | pennylane | openqasm (default: detect)")
        if needs_timeout:
            sp.add_argument("--timeout", type=float, help="sandbox timeout in seconds (max 120)")
        return sp

    fw = sub.add_parser("frameworks", help="list registered runtimes and their availability")
    fw.add_argument("--probe", action="store_true", help="also import each framework inside the sandbox")
    common("run", "execute code in the sandbox and report what happened")
    common("diagnose", "reproduce the failure and classify it")
    # run_fix detects the framework itself and applies the default sandbox
    # budget, so --framework/--timeout would be silently ignored here.
    common("fix", "propose a deterministic fix (never claims verification)",
           needs_framework=False, needs_timeout=False)
    common("validate", "execute this code and classify the result")
    common("solve", "full pipeline: reproduce -> diagnose -> fix -> execute -> verify", needs_framework=True)

    sub.add_parser("serve", help="start the HTTP API instead of running locally (see run.py)").set_defaults(
        _serve=True
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.sandbox_python:
        candidate = os.path.abspath(os.path.expanduser(args.sandbox_python))
        if not os.path.isfile(candidate):
            print(f"qresolve: no such interpreter: {candidate}", file=sys.stderr)
            return 2
        os.environ["QRESOLVE_SANDBOX_PYTHON"] = candidate
    handlers = {
        "frameworks": cmd_frameworks,
        "run": cmd_run,
        "diagnose": cmd_diagnose,
        "fix": cmd_fix,
        "validate": cmd_validate,
        "solve": cmd_solve,
    }
    if getattr(args, "_serve", False):
        print("qresolve: to serve the HTTP API run `python run.py` (that is the desktop/UI client).",
              file=sys.stderr)
        return 2
    handler = handlers[args.command]
    try:
        return handler(args)
    except CliError as exc:
        print(f"qresolve: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("qresolve: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
