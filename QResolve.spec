# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the QResolve desktop application.

Build from the repository root:  pyinstaller QResolve.spec
Output: dist/QResolve/QResolve.exe + _internal/ (ship _python/ next to it
for the sandboxed user-code interpreter; see desktop/qresolve_desktop.py).
"""
from PyInstaller.utils.hooks import collect_all

datas = [("frontend/dist", "web")]
binaries = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
]

for _pkg in ("qiskit", "pennylane", "cirq"):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

a = Analysis(
    ["desktop/qresolve_desktop.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.tests", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="QResolve",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="QResolve")
