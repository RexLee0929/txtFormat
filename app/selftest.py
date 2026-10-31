"""打包后自检（只在 ``--selftest`` / ``--menutest`` 时被导入）。

以前这两段（约 180 行）直接写在 :mod:`app.main` 里 —— 生产入口夹带一大坨
测试代码，既拖慢阅读，也让每条启动路径都跟着 import 一堆只有测试才用的模块。
现在拆成独立模块，``main()`` 里按参数懒加载，正常启动完全不碰这里。
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from .core.version import APP_VERSION


def _wait_events(app: QApplication, seconds: float) -> None:
    """处理事件并真实等待（等 DWM 合成完成，单靠 processEvents 不够）。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)


# ------------------------------------------------------------------ 全量自检
def selftest(app: QApplication, out_dir: str) -> int:
    """不弹窗，逐项验证资源、核心逻辑与渲染，结果写入 JSON。"""
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

    def icon_palette() -> str:
        """强调色确实从图标派生出来了（不是兜底种子）。"""
        from .core import accent
        h, s = accent.icon_seed()
        pal = accent.palette()
        assert pal["accent"].startswith("#") and len(pal["accent"]) == 7, pal
        fallback = (abs(h - accent.FALLBACK_H) < 1e-9 and abs(s - accent.FALLBACK_S) < 1e-9)
        assert not fallback, "取色退回兜底种子，说明 app.ico 没读到"
        return f"seed=({h:.3f},{s:.3f}) accent={pal['accent']}"

    def command_bar() -> str:
        """命令栏在窄窗口下收进溢出菜单、放大后必须全部回来。

        用户实测报过（缩小再放大，按钮文字不回来）—— 这是真实布局行为，
        只有跑真实事件循环才验得出来，所以放进打包自检。
        """
        from .ui.main_window import MainWindow
        win = MainWindow()
        win.resize(1700, 880)
        win.show()
        for _ in range(4):
            app.processEvents()

        def visible() -> int:
            return len(win.visible_command_labels())

        wide = visible()
        assert wide > 0, "命令栏没有显示任何按钮"
        win.resize(1000, 700)
        for _ in range(4):
            app.processEvents()
        narrow = visible()
        assert narrow < wide, f"缩小后没有收进溢出菜单：{narrow}/{wide}"
        win.resize(1700, 880)
        for _ in range(4):
            app.processEvents()
        back = visible()
        win.hide()
        assert back == wide, f"放大后按钮没恢复：{wide} -> {back}"
        return f"{wide} → {narrow} → {back} 个可见按钮"

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
    check("图标取色", icon_palette)
    check("命令栏缩放", command_bar)
    check("界面渲染", render)

    ok = all(c["ok"] for c in checks)
    report = {"ok": ok, "frozen": bool(getattr(sys, "frozen", False)),
              "version": APP_VERSION, "checks": checks}
    with open(os.path.join(out_dir, "selftest.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return 0 if ok else 1


# ------------------------------------------------------------------ 菜单自检
def menutest(app: QApplication, out_dir: str) -> int:
    """验证弹层圆角裁切（mask）真实生效。

    黑角是 DWM 合成层的问题（alpha 没生效时圆角外被当黑合成），而 Qt 6.12
    的弹层走 DirectComposition，GDI 抓屏根本抓不到它的内容（实测 BitBlt /
    PrintWindow 都返回全零）——所以不走截屏，直接验证系统级裁切本身：
    mask 必须把四个圆角排除在外、把卡片主体包进来。
    mask 生效时圆角外不存在像素，无论 DWM 怎么合成都不可能露出黑色。
    """
    import ctypes

    from .ui.main_window import MainWindow

    os.makedirs(out_dir, exist_ok=True)
    window = MainWindow()
    window.resize(1420, 880)
    window.show()
    window.raise_()
    window.activateWindow()
    _wait_events(app, 0.8)

    menu = window.menuBar().actions()[2].menu()
    menu.popup(window.mapToGlobal(QPoint(300, 60)))
    _wait_events(app, 0.6)

    mask = menu.mask()
    w, h = menu.width(), menu.height()
    corners_out = [not mask.contains(QPoint(x, y))
                   for x, y in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2))]
    body_in = [mask.contains(QPoint(x, y))
               for x, y in ((w // 2, h // 2), (10, h // 2), (w - 10, h // 2), (w // 2, 10))]

    donotround = None
    if sys.platform == "win32":
        try:
            val = ctypes.c_int(-1)
            ctypes.windll.dwmapi.DwmGetWindowAttribute(
                ctypes.c_void_p(int(menu.winId())), ctypes.c_uint(33),
                ctypes.byref(val), ctypes.sizeof(val))
            donotround = val.value          # 1 = DWMWCP_DONOTROUND
        except Exception:                   # noqa: BLE001
            donotround = None

    menu.close()
    window.hide()
    # DWM 对弹层不接受 CORNER_PREFERENCE（读回恒为默认值），但 mask 是系统级
    # 裁切、不依赖它 —— 判定只看 mask 是否把圆角裁掉。
    report = {"menu_size": [w, h],
              "corners_excluded": all(corners_out),
              "corners_out": corners_out,
              "body_included": all(body_in),
              "body_in": body_in,
              "dwm_donotround": donotround}
    report["ok"] = report["corners_excluded"] and report["body_included"]
    with open(os.path.join(out_dir, "menutest.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return 0 if report["ok"] else 1


__all__ = ["selftest", "menutest"]
