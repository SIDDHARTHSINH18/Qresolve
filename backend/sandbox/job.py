"""Windows Job Object resource limits for sandbox children (stdlib ctypes only).

Until now the sandbox bounded user code with a wall-clock timeout and process
isolation only: a program could commit unlimited memory, keep burning CPU after
the parent stopped waiting, or survive as an orphan grandchild. Windows can
bound all three in kernel, so this module wraps the handful of kernel32 calls
that do it — no third-party dependency, no extra binary to sign, and therefore
nothing new for an application-control policy to block.

Off Windows, and whenever a kernel call is refused (an outer job object that
forbids nesting or breakaway is the usual cause on developer machines), every
function here reports failure instead of raising: the caller must then say the
limits were not enforced rather than implying they were.
"""
from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass

PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001

# JOBOBJECTINFOCLASS values as the kernel numbers them: accounting is class 1
# and extended limits class 9. These are verified at runtime by writing a limit
# and reading the same struct back, because a wrong class number is refused (or
# worse, interpreted as another structure) rather than reported.
_JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_LIMIT_PROCESS_MEMORY = 0x00000100
_LIMIT_PROCESS_TIME = 0x00000002

_INVALID_HANDLE = ctypes.c_void_p(-1).value
_100NS_PER_SECOND = 10_000_000


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _BasicAccountingInformation(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", ctypes.c_uint32),
        ("TotalProcesses", ctypes.c_uint32),
        ("ActiveProcesses", ctypes.c_uint32),
        ("TotalTerminatedProcesses", ctypes.c_uint32),
    ]


@dataclass
class _Kernel32:
    create_job_object: object
    set_information_job_object: object
    assign_process_to_job_object: object
    query_information_job_object: object
    terminate_job_object: object
    open_process: object
    close_handle: object


_CACHED_API: _Kernel32 | None = None
_API_PROBED = False


def _load() -> _Kernel32 | None:
    global _CACHED_API, _API_PROBED
    if _API_PROBED:
        return _CACHED_API
    _API_PROBED = True
    if os.name != "nt":
        _CACHED_API = None
        return None
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        _CACHED_API = None
        return None

    handle = ctypes.c_void_p
    kernel32.CreateJobObjectW.restype = handle
    kernel32.CreateJobObjectW.argtypes = [handle, ctypes.c_wchar_p]
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.SetInformationJobObject.argtypes = [handle, ctypes.c_int, handle, ctypes.c_uint32]
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.AssignProcessToJobObject.argtypes = [handle, handle]
    kernel32.QueryInformationJobObject.restype = ctypes.c_int
    kernel32.QueryInformationJobObject.argtypes = [
        handle,
        ctypes.c_int,
        handle,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    kernel32.TerminateJobObject.restype = ctypes.c_int
    kernel32.TerminateJobObject.argtypes = [handle, ctypes.c_uint32]
    kernel32.OpenProcess.restype = handle
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [handle]
    api = _Kernel32(
        create_job_object=kernel32.CreateJobObjectW,
        set_information_job_object=kernel32.SetInformationJobObject,
        assign_process_to_job_object=kernel32.AssignProcessToJobObject,
        query_information_job_object=kernel32.QueryInformationJobObject,
        terminate_job_object=kernel32.TerminateJobObject,
        open_process=kernel32.OpenProcess,
        close_handle=kernel32.CloseHandle,
    )
    _CACHED_API = api
    return api


def _query_extended(api: _Kernel32, handle):
    info = _ExtendedLimitInformation()
    returned = ctypes.c_uint32(0)
    ok = api.query_information_job_object(
        handle,
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(info),
        ctypes.sizeof(info),
        ctypes.byref(returned),
    )
    return info if ok and returned.value else None


def _limits_applied(api: _Kernel32, handle, memory_bytes: int) -> bool:
    """Read the limits back: proof the kernel understood the call.

    Without this a wrong information class would be a silent no-op, and the
    sandbox would claim memory bounds it never set.
    """
    info = _query_extended(api, handle)
    if info is None:
        return False
    return (
        int(info.ProcessMemoryLimit) == memory_bytes
        and bool(info.BasicLimitInformation.LimitFlags & _LIMIT_PROCESS_MEMORY)
    )


class SandboxJob:
    """One bound child process, or None-worth of no-ops if the OS refused."""

    def __init__(self, api: _Kernel32, handle, memory_bytes: int, cpu_s: float) -> None:
        self._api = api
        self._handle = handle
        self.memory_bytes = memory_bytes
        self.cpu_s = cpu_s
        self.assigned = False

    @classmethod
    def open(cls, memory_bytes: int, cpu_s: float) -> SandboxJob | None:
        """Create a job with the limits applied, or None if unsupported/denied."""
        api = _load()
        if api is None:
            return None
        handle = api.create_job_object(None, None)
        if not handle or handle == _INVALID_HANDLE:
            return None

        info = _ExtendedLimitInformation()
        flags = _LIMIT_KILL_ON_JOB_CLOSE | _LIMIT_PROCESS_MEMORY | _LIMIT_PROCESS_TIME
        info.BasicLimitInformation.LimitFlags = flags
        info.ProcessMemoryLimit = memory_bytes
        info.BasicLimitInformation.PerProcessUserTimeLimit = int(cpu_s * _100NS_PER_SECOND)
        ok = api.set_information_job_object(
            handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok or not _limits_applied(api, handle, memory_bytes):
            api.close_handle(handle)
            return None
        return cls(api, handle, memory_bytes, cpu_s)

    def assign(self, pid: int) -> bool:
        """Bind the freshly created child to this job. False means no limits."""
        if self._handle is None:
            return False
        process = self._api.open_process(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, pid)
        if not process or process == _INVALID_HANDLE:
            return False
        try:
            self.assigned = bool(self._api.assign_process_to_job_object(self._handle, process))
        finally:
            self._api.close_handle(process)
        return self.assigned

    def kill(self) -> bool:
        """Terminate every process still inside the job (whole tree)."""
        if self._handle is None:
            return False
        return bool(self._api.terminate_job_object(self._handle, 1))

    def peak_memory_bytes(self) -> int | None:
        if self._handle is None:
            return None
        info = _query_extended(self._api, self._handle)
        return None if info is None else int(info.PeakProcessMemoryUsed)

    def cpu_time_s(self) -> float | None:
        if self._handle is None:
            return None
        accounting = _BasicAccountingInformation()
        returned = ctypes.c_uint32(0)
        ok = self._api.query_information_job_object(
            self._handle,
            _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(accounting),
            ctypes.sizeof(accounting),
            ctypes.byref(returned),
        )
        if not ok or not returned.value:
            return None
        return (int(accounting.TotalUserTime) + int(accounting.TotalKernelTime)) / _100NS_PER_SECOND

    def close(self) -> None:
        """Release the job; KILL_ON_JOB_CLOSE reaps anything still running."""
        handle, self._handle = self._handle, None
        if handle:
            self._api.close_handle(handle)


def limit_report(job: SandboxJob | None, exit_code: int | None) -> str | None:
    """Explain a run the kernel stopped, or None when the limits look unused.

    Only consulted for a run that produced no result, so a program that simply
    raised an exception never gets a misleading resource-limit message.
    """
    if job is None or not job.assigned or exit_code == 0:
        return None
    peak = job.peak_memory_bytes()
    if peak is not None and peak >= job.memory_bytes:
        return (
            f"Terminated by the sandbox: committed memory reached the "
            f"{job.memory_bytes // (1024 * 1024)} MB limit."
        )
    cpu = job.cpu_time_s()
    if cpu is not None and cpu >= job.cpu_s:
        return (
            f"Terminated by the sandbox: CPU time reached the {job.cpu_s:g} s per-process limit."
        )
    return None
