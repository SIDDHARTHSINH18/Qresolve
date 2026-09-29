"""Sandbox: isolated subprocess execution of submitted code.

Enforced: a fresh subprocess in a temporary working directory that is deleted
afterwards, a scrubbed environment, CPython isolated mode (`-I -B -X utf8`), a
hard wall-clock timeout, output caps, and - on Windows - a kernel job object
that caps committed memory and per-process CPU time and kills the entire child
tree, including an orphaned grandchild (see backend/sandbox/job.py). When the
OS refuses that job object the run says so on stderr instead of implying the
bounds held.

NOT enforced, on any platform: filesystem and network isolation. The child
runs with this process's own OS permissions, so this is a guardrail against
accidents and runaway code, not a container, chroot or OS jail. Execute only
code you are willing to run as the current user.
"""
from backend.sandbox.executor import SandboxLimits, SandboxResult, run_python_code

__all__ = ["SandboxLimits", "SandboxResult", "run_python_code"]
