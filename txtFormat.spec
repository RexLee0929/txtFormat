# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir）。

    python -m PyInstaller --noconfirm --clean --distpath artifacts txtFormat.spec

产物：artifacts/txtFormat/txtFormat.exe（免安装，双击即用）
"""

import os
import re

APP_NAME = "txtFormat"

# ---- 版本：唯一来源是 installer/version.props（规范 §十三.8）----
# exe 的版本资源（文件属性 → 详细信息）在这里现生成、写进 build/，
# 仓库里不存手写的版本资源文件；改版本只改 props：
#   · 运行期 app/core/version.py 读 props（随包进 exe，datas 里有）；
#   · 打包期本脚本读 props 生成 PE 版本资源；
#   · 安装器 csproj Import 同一份 props。
_PROPS_TEXT = open(os.path.join(SPECPATH, "installer", "version.props"),
                   encoding="utf-8").read()


def _field(name: str, default: str = "") -> str:
    m = re.search(rf"<{name}>([^<]+)</{name}>", _PROPS_TEXT)
    return m.group(1).strip() if m else default


VERSION = _field("Version")
COMPANY = _field("Company", "Rex Lee")
PRODUCT = _field("Product", APP_NAME)
if not VERSION:
    raise SystemExit("installer/version.props 里读不到 <Version>：版本资源宁可不打包，也不写死")

_QUAD = tuple(([int(x) for x in VERSION.split(".")] + [0, 0, 0, 0])[:4])
_QUAD_S = ".".join(str(x) for x in _QUAD)

_BUILD_DIR = os.path.join(SPECPATH, "build")
os.makedirs(_BUILD_DIR, exist_ok=True)
VERSION_FILE = os.path.join(_BUILD_DIR, "file_version.txt")
with open(VERSION_FILE, "w", encoding="utf-8") as _fh:
    _fh.write(f"""# UTF-8
# 由 txtFormat.spec 从 installer/version.props 现生成 —— 不手改，改版本只改 props
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={_QUAD},
    prodvers={_QUAD},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'080404B0',
          [StringStruct(u'CompanyName', u'{COMPANY}'),
           StringStruct(u'FileDescription', u'{PRODUCT}'),
           StringStruct(u'FileVersion', u'{_QUAD_S}'),
           StringStruct(u'InternalName', u'{APP_NAME}'),
           StringStruct(u'LegalCopyright', u'{_field("Copyright")}'),
           StringStruct(u'LegalTrademarks', u''),
           StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
           StringStruct(u'ProductName', u'{PRODUCT}'),
           StringStruct(u'ProductVersion', u'{VERSION}'),
           StringStruct(u'Comments', u'作者 {_field("Authors", COMPANY)}    联系邮箱 rexlee@rexleepro.com'),
           StringStruct(u'PrivateBuild', u''),
           StringStruct(u'SpecialBuild', u'')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)
""")

datas = [
    ("app/data", "app/data"),        # 词表：错别字 / 屏蔽码 / 拼音 + ABOUT.md
    ("app/assets", "app/assets"),    # 图标
    # 版本号的唯一来源（规范 §一）：随包进 exe，运行期与开发期读同一份文件
    (os.path.join("installer", "version.props"), "."),
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
