"""打包后自检（只在 ``--selftest`` / ``--menutest`` 时被导入）。

以前这两段（约 180 行）直接写在 :mod:`app.main` 里 —— 生产入口夹带一大坨
测试代码，既拖慢阅读，也让每条启动路径都跟着 import 一堆只有测试才用的模块。
现在拆成独立模块，``main()`` 里按参数懒加载，正常启动完全不碰这里。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QWidget

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

    def about_text() -> str:
        """关于文案从 ABOUT.md 读（规范 §八：文案不进代码）+ 占位符已替换。"""
        from .core import aboutmd
        assert aboutmd.md_path(), "找不到 ABOUT.md（没打进包？）"
        raw = aboutmd.read_md()
        assert raw.strip(), "ABOUT.md 是空的"
        html_text = aboutmd.render(accent="#000000")
        left = [k for k in aboutmd.placeholders() if k in html_text]
        assert not left, f"占位符没替换：{left}"
        assert "©" in html_text, "页脚（© 行）没渲出来"
        return f"{len(raw)} 字符源文 → {len(html_text)} 字符 HTML"

    def version_source() -> str:
        """版本号确实从 version.props 读到（规范 §一：单源，不许手写）。"""
        from .core import version
        assert version.APP_VERSION != version.FALLBACK_VERSION, \
            f"版本号退回兜底值 {version.FALLBACK_VERSION}，说明 version.props 没打进包"
        assert re.fullmatch(r"\d+(\.\d+)+", version.APP_VERSION), version.APP_VERSION
        return f"{version.APP_VERSION}（来源 {version.VERSION_FILE}）"

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

    def instance_key() -> str:
        """单实例管道名必须带**程序目录**散列（安装版 / 绿色版不能互相抢）。

        打包后取的是 ``sys.executable`` 所在目录 —— 不能用 ``__file__``：
        PyInstaller 每次解包到不同的 _MEIPASS 临时目录，散列每次都会变，
        单实例就彻底失效了。这条只有在 exe 里跑才有意义，所以放进打包自检。
        """
        from .main import _INSTANCE_KEY, _app_dir
        assert re.search(r"-[0-9a-f]{8}$", _INSTANCE_KEY), _INSTANCE_KEY
        base = _app_dir()
        assert os.path.isdir(base), base
        if getattr(sys, "frozen", False):
            assert os.path.normcase(base) == os.path.normcase(
                os.path.dirname(os.path.abspath(sys.executable))), base
        return f"{_INSTANCE_KEY} ← {base}"

    check("核心格式整理", core_format)
    check("内置词表", data_files)
    check("关于文案", about_text)
    check("正则库", regex_lib)
    check("设置读写", settings_roundtrip)
    check("图标取色", icon_palette)
    check("版本来源", version_source)
    check("单实例命名", instance_key)
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

    # ---- 规范 §十：菜单结构四断言（把「凑数空菜单」「删着删着把帮助删了」挡在
    # 第一轮验证里）。数据表与建出来的菜单树**两处都验**：只验界面会漏掉「表里
    # 有、界面上没建」，只验表会漏掉建树漏项。
    from .ui import menu_def

    bar = window.menuBar().actions()
    has_two = len(bar) >= 2
    nonempty = all(a.menu() is not None and any(
        x.isEnabled() and not x.isSeparator() for x in a.menu().actions()) for a in bar)
    help_act = next((a for a in bar
                     if a.text().replace("&", "").startswith("帮助")), None)
    has_help = help_act is not None
    about_in_menu = bool(help_act and help_act.menu() and any(
        x.data() == menu_def.ABOUT_CMD for x in help_act.menu().actions()))
    about_in_table = any(item.cmd == menu_def.ABOUT_CMD for item in menu_def.all_items())
    structure = {
        "groups": len(bar),
        "has_two_groups": has_two,
        "every_group_nonempty": nonempty,
        "has_help_group": has_help,
        "about_in_menu": about_in_menu,
        "about_in_table": about_in_table,
    }
    structure_ok = all((has_two, nonempty, has_help, about_in_menu, about_in_table))

    # DWM 对弹层不接受 CORNER_PREFERENCE（读回恒为默认值），但 mask 是系统级
    # 裁切、不依赖它 —— 判定只看 mask 是否把圆角裁掉。
    report = {"menu_size": [w, h],
              "corners_excluded": all(corners_out),
              "corners_out": corners_out,
              "body_included": all(body_in),
              "body_in": body_in,
              "dwm_donotround": donotround,
              "structure": structure}
    report["ok"] = (report["corners_excluded"] and report["body_included"]
                    and structure_ok)
    with open(os.path.join(out_dir, "menutest.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return 0 if report["ok"] else 1


def popuptest(app: QApplication, out_dir: str) -> int:
    """验证下拉弹层与唤起它的字段**严格同宽**（用户报过两次「弹层超出去」）。

    只测几何、不靠肉眼：宽度必须一字不差等于字段宽（差 1px 都算失败），
    左缘必须与字段左缘对齐，高度不得超过声明行数。同时把整屏截图存进
    输出目录 —— 弹层是独立顶层窗口，``grab()`` 抓不到，只能抓桌面。

    这个入口存在的原因：几何问题在开发机上会被字体/缩放的偶然取值掩盖
    （条目恰好比字段窄时，旧实现 ``max(字段宽, 最宽项+30)`` 也算出字段宽，
    本地一切正常、用户那边却明显溢出），只有让**打包后的程序**自己量，
    才是可复现的证据。
    """
    from .ui.fontdialog import FontDialog

    os.makedirs(out_dir, exist_ok=True)
    dialog = FontDialog("Microsoft YaHei UI", 12, 400, False, 160)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    _wait_events(app, 0.6)

    dialogs_right = dialog.geometry().right()
    rows: dict[str, dict] = {}
    for key, box in (("size", dialog.size_box), ("line", dialog.line_box),
                     ("weight", dialog.weight_box)):
        box.showPopup()
        _wait_events(app, 0.4)
        popup = box.view().window()
        field_w = box.width()
        origin = box.mapToGlobal(box.rect().topLeft())
        screen = app.primaryScreen()
        if screen is not None:
            screen.grabWindow(0).save(os.path.join(out_dir, f"popup_{key}.png"))
        geo = popup.geometry()
        rows[key] = {
            "field_width": field_w,
            "popup_width": popup.width(),
            "popup_height": popup.height(),
            "left_delta": popup.geometry().left() - origin.x(),
            "overflow_right": popup.geometry().right() - dialogs_right,
            "rows_max": box._rows,
            # 弹层全局矩形（逻辑像素）+ 屏幕 DPR：截图是物理像素，放大查边框/
            # 阴影/圆角时按这两个值换算裁剪，别靠肉眼估坐标（实测会裁到别的窗口）。
            "popup_rect": [geo.x(), geo.y(), geo.width(), geo.height()],
            "dpr": screen.devicePixelRatio() if screen is not None else 1.0,
            # 上下滚动提示箭头：列表超过显示行数时 Qt 会插两条灰色横带
            # （QComboBoxPrivateScroller，样式表够不着）—— 已隐藏，这里强断言。
            # offscreen 测试平台不产生 scroller，只有真实窗口才有，所以放这。
            "scrollers_visible": sum(
                1 for c in popup.findChildren(QWidget)
                if c.metaObject().className() == "QComboBoxPrivateScroller"
                and c.isVisible()),
        }
        box.hidePopup()
        _wait_events(app, 0.2)
    dialog.close()

    # 判定：宽严格相等 + 左缘对齐（±1 容差给整数取整）+ 不出对话框右缘 + 无箭头
    for info in rows.values():
        info["ok"] = (info["popup_width"] == info["field_width"]
                      and abs(info["left_delta"]) <= 1
                      and info["overflow_right"] <= 0
                      and info["scrollers_visible"] == 0)
    report = {"popups": rows, "ok": all(i["ok"] for i in rows.values())}
    with open(os.path.join(out_dir, "popuptest.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return 0 if report["ok"] else 1


__all__ = ["selftest", "menutest", "popuptest"]
