"""程序入口。"""

from __future__ import annotations

import ctypes
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .core.paths import asset
from .core.version import APP_NAME, APP_VERSION, APP_TITLE
from .ui.main_window import MainWindow


def _enable_win11_chrome(hwnd: int | None = None) -> None:
    """按《程序本体设计规范》§四定制系统标题栏（失败时静默跳过）。

    caption 色与内容区底色一致，标题栏和内容区看起来是一体的；
    border 比 caption 深一档，看得见窗口边界但不刺眼。
    Win11 的 DWM 用 COLORREF（0x00BBGGRR），不是 RGB —— 顺序别写反。
    """
    if sys.platform != "win32":
        return

    def rgb(r: int, g: int, b: int) -> int:
        return (b << 16) | (g << 8) | r

    try:
        from .ui.theme import Color

        def hex_to_colorref(value: str) -> int:
            value = value.lstrip("#")
            r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
            return rgb(r, g, b)

        dwmapi = ctypes.WinDLL("dwmapi")
        handle = hwnd if hwnd is not None else ctypes.windll.user32.GetActiveWindow()

        def set_attr(attr: int, value: int) -> None:
            v = ctypes.c_int(value)
            dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(handle), ctypes.c_uint(attr),
                                         ctypes.byref(v), ctypes.sizeof(v))

        set_attr(20, 0)                                  # DWMWA_USE_IMMERSIVE_DARK_MODE = 浅色
        set_attr(33, 2)                                  # 圆角
        set_attr(34, hex_to_colorref("#E8E8E8"))         # 边框色，比 caption 深一档
        set_attr(35, hex_to_colorref(Color.window))      # caption = 内容区底色 #F3F3F3
        set_attr(36, hex_to_colorref(Color.text))        # 标题文字 #1B1B1B
        set_attr(38, 0)                                  # 保持纯色背景，保证文字可读
    except Exception:       # noqa: BLE001 - 老系统上失败不影响使用
        pass


def _selftest(app: QApplication, out_dir: str) -> int:
    """打包后自检：不弹窗，逐项验证资源、核心逻辑与渲染，结果写入 JSON。"""
    import json
    import traceback

    checks: list[dict[str, object]] = []
    os.makedirs(out_dir, exist_ok=True)

    def check(name: str, fn) -> None:
        try:
            detail = fn()
            checks.append({"name": name, "ok": True, "detail": str(detail)})
        except Exception as exc:                     # noqa: BLE001 - 自检要记录一切
            checks.append({"name": name, "ok": False, "detail": f"{exc}",
                           "trace": traceback.format_exc(limit=3)})

    def core_format() -> str:
        from .core import formatter
        from .core.settings import Settings
        text = "第一行没有标点\n还是这句,逗号是半角.\n\n\n\n第二段，OK。"
        result = formatter.format_text(text, Settings())
        assert "半角" in result.text
        return result.text.replace("\n", "\\n")[:80]

    def data_files() -> str:
        from .core.paths import data_dir
        found = []
        for name in ("typos.txt", "screened.txt", "pinyin.txt"):
            path = os.path.join(data_dir(), name)
            assert os.path.exists(path), path
            found.append(f"{name}={os.path.getsize(path)}B")
        return ", ".join(found)

    def regex_lib() -> str:
        import re

        from .core.regexlib import RegexLibrary
        lib = RegexLibrary()
        assert len(lib.entries) >= 80, len(lib.entries)
        bad = []
        for entry in lib.entries:
            try:
                entry.regex
            except re.error:
                bad.append(entry.name)
        return f"{len(lib.entries)} 条，编译失败 {len(bad)} 条"

    def settings_roundtrip() -> str:
        from .core import settings as settings_mod
        st = settings_mod.Settings()
        st.font_size = 13
        probe = os.path.join(out_dir, "_roundtrip-config.json")
        st.save(probe)
        assert os.path.isfile(probe), probe
        st2 = settings_mod.Settings.load(probe)
        os.remove(probe)
        assert st2.font_size == 13, st2.font_size
        # 顺手报告正式设置路径，确认它落在 exe 同目录（规范 §十）
        assert settings_mod.SETTINGS_PATH, settings_mod.SETTINGS_PATH
        return "SETTINGS_PATH=" + settings_mod.SETTINGS_PATH

    def render() -> str:
        from .ui.main_window import MainWindow
        window = MainWindow()
        window.resize(1440, 900)
        window.editor.setPlainText("第1章 自检\n\n　　这是一段用于打包自检的文字。\n")
        window.show()
        app.processEvents()
        target = os.path.join(out_dir, "selftest-window.png")
        window.grab().save(target)
        # 不能调 window.close()：closeEvent 会走 _confirm_discard 弹模态确认框，
        # 自检无人应答就永远挂住；hide() 不触发 closeEvent，也不会落盘设置。
        window.hide()
        assert os.path.getsize(target) > 20000, target
        return target

    check("核心格式整理", core_format)
    check("内置词表", data_files)
    check("正则库", regex_lib)
    check("设置读写", settings_roundtrip)
    check("界面渲染", render)

    ok = all(c["ok"] for c in checks)
    report = {"ok": ok, "frozen": bool(getattr(sys, "frozen", False)),
              "version": APP_VERSION, "checks": checks}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "selftest.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return 0 if ok else 1


def main() -> int:
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    # 不设置 applicationDisplayName：Qt 会把「程序显示名」追加到窗口标题后面，
    # 导致标题栏出现「文件名 — txtFormat 1.0.1 - txtFormat」这种重复尾巴。
    app.setApplicationDisplayName("")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("txtFormat")
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))

    icon_path = asset("app.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 隐藏自检入口：txtFormat.exe --selftest <输出目录>
    if "--selftest" in sys.argv:
        index = sys.argv.index("--selftest")
        out_dir = sys.argv[index + 1] if len(sys.argv) > index + 1 else os.getcwd()
        return _selftest(app, os.path.abspath(out_dir))

    window = MainWindow()
    window.show()
    # 窗口已建出真实句柄后再定制标题栏（过早调用拿不到有效的 hwnd）
    _enable_win11_chrome(int(window.winId()))

    # 命令行传入的文件直接打开
    for arg in sys.argv[1:]:
        if os.path.isfile(arg):
            window.open_path(os.path.abspath(arg))
            break

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
