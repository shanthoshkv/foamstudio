# -*- mode: python ; coding: utf-8 -*-
# Phase 2 collects Qt WebEngine for the case generator (ADR-0006).
# Qt Charts and Qt Data Visualization stay excluded.

import os

from PyInstaller.utils.hooks import collect_data_files

root = os.path.abspath(os.path.join(SPECPATH, os.pardir))

a = Analysis(
    [os.path.join(root, "foamstudio", "__main__.py")],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(root, "openfoam_case_generator.html"), "."),
        (os.path.join(root, "tests", "headless.js"), "tests"),
        (os.path.join(root, "tests", "gen.js"), "tests"),
        # theme qss/svg and i18n catalogs (pyproject package-data)
        *collect_data_files("foamstudio"),
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
        # unused Qt modules; WebEngine still needs Qml/Quick, so those stay
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
        "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras", "PySide6.QtQuick3D",
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
        "PySide6.QtGraphs", "PySide6.QtGraphsWidgets", "PySide6.QtLocation",
        "PySide6.QtPositioning", "PySide6.QtSensors", "PySide6.QtBluetooth", "PySide6.QtNfc",
        "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtTextToSpeech",
        "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtDesigner",
        "PySide6.QtHttpServer", "PySide6.QtWebSockets",
        "tkinter",
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
