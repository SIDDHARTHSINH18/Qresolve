"""Sandbox: isolated subprocess execution of submitted code.

Limitations (documented deliberately):
- Isolation is a fresh subprocess in a temp working dir with a scrubbed
  environment and CPython isolated mode (`-I`). It is NOT a container,
  chroot, or OS-level jail; code can technically touch the filesystem or
  network within the OS user's permissions.
- No CPU/memory rlimits on Windows; timeout and output caps are enforced.
- Run only in a trusted/dev environment until a containerized executor exists.
"""
from backend.sandbox.executor import SandboxLimits, SandboxResult, run_python_code

__all__ = ["SandboxLimits", "SandboxResult", "run_python_code"]
