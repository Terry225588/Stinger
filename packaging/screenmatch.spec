# -*- mode: python ; coding: utf-8 -*-
# SPECPATH is the directory that contains this file (packaging/).
# The entry script is the repository root main.py, not packaging/main.py.

from pathlib import Path

import sys

from PyInstaller.utils.hooks import collect_all

_spec_dir = Path(SPECPATH).resolve()
if _spec_dir.is_file():
    _spec_dir = _spec_dir.parent
sys.path.insert(0, str(_spec_dir))
from locate_entry import resolve_entry

entry = resolve_entry(_spec_dir)
root = entry.parent
if not entry.is_file():
    raise SystemExit("missing entry script: " + str(entry))

datas = [
    (str(root / "assets" / "stinger.ico"), "assets"),
    (str(root / "assets" / "stinger-app-icon.jpg"), "assets"),
    (str(root / "assets" / "stinger-question-template.xlsx"), "assets"),
]
binaries = []
hiddenimports = ["screenmatch", "screenmatch.app", "screenmatch.panel", "openpyxl", "mss"]

for package in ("rapidocr_onnxruntime", "onnxruntime", "cv2", "shapely"):
    collected_datas, collected_binaries, collected_hidden = collect_all(package)
    datas += collected_datas
    binaries += collected_binaries
    hiddenimports += collected_hidden

a = Analysis(
    [str(entry)],
    pathex=[str(root / "src"), str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Stinger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(root / "assets" / "stinger.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Stinger",
)
