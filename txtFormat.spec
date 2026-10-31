# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir）。

    python -m PyInstaller --noconfirm --clean --distpath artifacts txtFormat.spec

产物：artifacts/txtFormat/txtFormat.exe（免安装，双击即用）
"""

import os

APP_NAME = "txtFormat"
VERSION_FILE = os.path.join("tools", "version_info.txt")

datas = [
    ("app/data", "app/data"),        # 词表：错别字 / 屏蔽码 / 拼音
    ("app/assets", "app/assets"),    # 图标
]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "pytest",
        "numpy",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ---- 精简：去掉用不到的 Qt 组件（软件 OpenGL、多语言翻译、多余插件）
# 注意：QtNetwork 不能删 —— 单实例互斥用 QLocalServer/QLocalSocket（规范 §七.6），
# 删掉 Qt6Network.dll 后 frozen 版会在 import 阶段直接失败（弹「Failed to execute
# script」且无人应答就挂住，实测踩过）。
DROP_FILES = {
    "PySide6/opengl32sw.dll",       # 软件 OpenGL 兜底，纯控件渲染用不到（19 MB）
    "PySide6/plugins/platforms/qoffscreen.dll",
    "PySide6/plugins/platforms/qminimal.dll",
    "PySide6/plugins/platforms/qdirect2d.dll",
    "PySide6/plugins/imageformats/qtiff.dll",
    "PySide6/plugins/imageformats/qtga.dll",
    "PySide6/plugins/imageformats/qwbmp.dll",
    "PySide6/plugins/imageformats/qicns.dll",
    "PySide6/plugins/imageformats/qwebp.dll",
}
DROP_PREFIXES = (
    "PySide6/translations/",        # 界面文案全为自定义，Qt 内置翻译用不到（6.7 MB）
    "PySide6/plugins/tls/",
    "PySide6/plugins/networkinformation/",
)


def _normalized(name: str) -> str:
    return name.replace("\\", "/")


a.binaries = [b for b in a.binaries
              if _normalized(b[0]) not in DROP_FILES
              and not _normalized(b[0]).startswith(DROP_PREFIXES)]
a.datas = [d for d in a.datas
           if _normalized(d[0]) not in DROP_FILES
           and not _normalized(d[0]).startswith(DROP_PREFIXES)]

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # 不用 UPX，避免杀毒误报
    console=False,                  # 窗口程序，不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join("app", "assets", "app.ico"),
    version=VERSION_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
