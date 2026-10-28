# -*- mode: python ; coding: utf-8 -*-
# Phase 2 collects Qt WebEngine for the case generator (ADR-0006).
# Qt Charts and Qt Data Visualization stay excluded.

import os

root = os.path.abspath(os.path.join(SPECPATH, os.pardir))

a = Analysis(
    [os.path.join(root, "foamstudio", "__main__.py")],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(root, "openfoam_case_generator.html"), "."),
        (os.path.join(root, "tests", "headless.js"), "tests"),
        (os.path.join(root, "tests", "gen.js"), "tests"),
    ],
    hiddenimports=[
        "PySide6.QtSvg",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="foamstudio",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="foamstudio")
