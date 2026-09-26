# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the QResolve desktop application.

Dev build   (repository root):  pyinstaller --noconfirm QResolve.spec
Installer build:               pyinstaller --noconfirm --distpath dist/install \\
                               --workpath build/install QResolve.spec
Both emit <dist>/QResolve/QResolve.exe + _internal/.

`_python/` (the embedded interpreter for sandboxed user code) is NOT produced
by this spec — COLLECT wipes its output directory, so it must be copied in
after every build:  cp -r build_package/_python <dist>/QResolve/_python
See desktop/qresolve_desktop.py:_bundled_python().
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
    console=False,  # M6: windowed app — no CMD window, ever (tkinter control UI + browser UI)
    version="installer/version_info.txt",  # M7: PE ProductName/FileVersion metadata
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="QResolve")
