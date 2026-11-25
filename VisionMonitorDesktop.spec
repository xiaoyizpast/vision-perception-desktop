# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：生成开箱即用的 VisionMonitorDesktop.exe 绿色桌面发行包。"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None

# 收集 ultralytics 配置文件（含 bytetrack.yaml / default.yaml）
datas = []
datas += collect_data_files("ultralytics")

binaries = []
binaries += collect_dynamic_libs("cv2")
binaries += collect_dynamic_libs("torchvision")

# 显式收集 torchvision 目录下的全部 .pyd / .dll（含 torchvision 0.29+ 的 _C_stable.pyd / image_stable.pyd / nvjpeg64_13.dll 等）
# 必须保留在 torchvision/ 子目录内，供 torchvision.extension._load_library("_C_stable") 精准加载
import torchvision as _tv
_tv_dir = Path(_tv.__file__).resolve().parent
for _bin in _tv_dir.iterdir():
    if _bin.is_file() and _bin.suffix.lower() in {".pyd", ".dll"}:
        binaries.append((str(_bin), "torchvision"))

hiddenimports = [
    "lap",
    "lapx",
    "scipy.optimize",
    "scipy.spatial.distance",
    "ultralytics.trackers.byte_tracker",
    "ultralytics.trackers.bot_sort",
    "ultralytics.trackers.track",
    "ultralytics.models.yolo.detect",
    "ultralytics.nn.tasks",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
]
hiddenimports += collect_submodules("ultralytics.trackers")

# 排除本桌面客户端不需要的巨型 WebEngine / 3D / QML / Notebook 冗余模块，大幅缩减体积
excludes = [
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DAnimation",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.QtQml",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtLocation",
    "PySide6.QtPositioning",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "tkinter",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
]

a = Analysis(
    ["main.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VisionMonitorDesktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="VisionMonitorDesktop",
)
