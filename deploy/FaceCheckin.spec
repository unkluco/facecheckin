# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).parent
backend_dir = project_root / "backend"
user_model_root = Path.home() / ".insightface" / "models"

datas = [
    (str(backend_dir / "static"), "backend/static"),
    (str(backend_dir / "recognition_settings.json"), "backend"),
]

buffalo_l = user_model_root / "buffalo_l"
if buffalo_l.exists():
    datas.append((str(buffalo_l), "models/insightface/buffalo_l"))

hiddenimports = [
    "aiohttp",
    "aiofiles",
    "cv2",
    "numpy",
    "onnxruntime",
    "insightface",
    "insightface.app",
    "insightface.model_zoo",
    "qrcode",
    "PIL",
    "pystray",
]


a = Analysis(
    [str(backend_dir / "tray_launcher.py")],
    pathex=[str(project_root), str(backend_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FaceCheckin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FaceCheckin",
)
