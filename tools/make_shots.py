#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重新生成 docs/screenshots 下的界面截图（README 引用的那些）。

    .venv\\Scripts\\python.exe tools\\make_shots.py            # 全部
    .venv\\Scripts\\python.exe tools\\make_shots.py main-window about reading

用真实窗口渲染（QWidget.grab），字体与系统强调色才正确；
离屏平台（offscreen）渲染出来的样式不完整，不要用。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtGui import QFont                                  # noqa: E402
from PySide6.QtWidgets import QApplication                       # noqa: E402

from app.ui import dialogs                                       # noqa: E402
from app.ui.main_window import MainWindow                        # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "screenshots")
SAMPLES = os.path.join(ROOT, "tests", "samples")

SAMPLE = """第1章 开端

　　他慢慢的说,这件事很奇怪。第二天早上,他醒了过来,发现自己躺在床上,身上盖着被子,窗外阳光明媚,鸟语花香,一切看起来都很正常,但是他心里总觉得有什么地方不太对劲。

　　“你醒了?”一个声音从门口传来。

　　少*妇站在门口,手里端着一碗热汤。

16K小说网 更新时间:2010-3-4 13:02:57 本章字数:4143

第2章 发展

　　接下来的几天,他一直在思考这个问题。必竟这件事关系到所有人,按纳不住心中的疑惑,他决定去找老张问个明白。

　　老张住在城东的一条小巷里,门口种着一棵老槐树。他敲了敲门,没有人应,便推门走了进去。
"""


def new_window(app: QApplication, width: int = 1420, height: int = 880) -> MainWindow:
    win = MainWindow()
    win.resize(width, height)
    win._set_text(SAMPLE, None)
    win.show()
    app.processEvents()
    return win


def load_samples(win: MainWindow, app: QApplication) -> None:
    os.makedirs(SAMPLES, exist_ok=True)
    for name in ("都市少帅 第01卷.txt", "都市少帅 第02卷.txt"):
        path = os.path.join(SAMPLES, name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(SAMPLE)
    win.file_panel.load_directory(SAMPLES)
    app.processEvents()


def save(widget, name: str) -> None:
    path = os.path.join(OUT_DIR, name)
    pm = widget.grab()
    pm.save(path)
    print(f"  {name}  {pm.width()}×{pm.height()}  ({os.path.getsize(path) // 1024} KB)")


# ---------------------------------------------------------------- 各张图
def shot_main(app: QApplication) -> None:
    win = new_window(app)
    load_samples(win, app)
    # 内容与打开时不同 → 「还原」按钮点亮
    win.editor.setPlainText(SAMPLE + "\n　　多出来的一行。\n")

    # 选一条较长的内置正则，展示多行查找框与「常用正则表达式」常驻列表
    panel = win.replace_panel
    idx = next((i for i, e in enumerate(win.lib.entries) if "屏蔽字" in e.name), -1)
    if idx >= 0:
        panel.library.setCurrentRow(idx + 1)       # 第 0 行是「（不使用）」
    app.processEvents()
    save(win, "main-window.png")
    win.close()


def _menu_shot(app: QApplication, prefix: str, name: str) -> None:
    win = new_window(app)
    load_samples(win, app)
    app.processEvents()
    for action in win.menuBar().actions():
        if action.text().startswith(prefix):
            menu = action.menu()
            menu.popup(win.mapToGlobal(win.menuBar().pos()))
            app.processEvents()
            save(menu, name)
            menu.close()
            break
    win.close()


def shot_menu(app: QApplication) -> None:
    """展开「文件」菜单，核对白色圆角卡片 / 左侧图标 / 右侧快捷键。"""
    _menu_shot(app, "文件", "menu.png")


def shot_menu_tools(app: QApplication) -> None:
    """展开「工具」菜单（图标最多，最看得出图标是否齐全）。"""
    _menu_shot(app, "工具", "menu-tools.png")


def shot_menu_view(app: QApplication) -> None:
    """展开「查看」菜单，核对可勾选项与勾选位置。"""
    _menu_shot(app, "查看", "menu-view.png")


def shot_main_popup(app: QApplication) -> None:
    """抓「转换方式」下拉的弹层，用于核对弹层不再出现接缝/小三角。

    「常用正则表达式」已由下拉改为常驻固定列表，不再有弹层可抓。
    """
    win = new_window(app)
    load_samples(win, app)
    app.processEvents()

    win.convert_combo.showPopup()
    app.processEvents()
    save(win.convert_combo.view().window(), "popup-convert.png")
    win.convert_combo.hidePopup()
    app.processEvents()
    win.close()


def shot_reading(app: QApplication) -> None:
    win = new_window(app)
    load_samples(win, app)
    win.apply_reading_mode(True)
    app.processEvents()
    save(win, "reading.png")
    win.close()


def shot_about(app: QApplication) -> None:
    win = new_window(app, 1000, 700)
    about = dialogs.AboutDialog(win)
    about.show()
    app.processEvents()
    save(about, "about.png")
    about.close()
    win.close()


def shot_options(app: QApplication) -> None:
    win = new_window(app, 1100, 800)
    dlg = dialogs.OptionsDialog(win.settings, win)
    dlg.show()
    app.processEvents()
    save(dlg, "options.png")
    dlg.close()
    win.close()


def shot_chapter(app: QApplication) -> None:
    win = new_window(app, 1100, 800)
    dlg = dialogs.SplitDialog(win.editor.toPlainText(), win.settings, win)
    dlg.show()
    app.processEvents()
    save(dlg, "chapter.png")
    dlg.close()
    win.close()


def shot_review(app: QApplication) -> None:
    win = new_window(app, 1100, 800)
    win.editor.setPlainText(SAMPLE)
    app.processEvents()
    dlg = dialogs.QuickReviewDialog(win.editor.toPlainText(), win)
    dlg.show()
    app.processEvents()
    save(dlg, "review.png")
    dlg.close()
    win.close()


SHOTS = {
    "main-window": shot_main,
    "menu": shot_menu,
    "menu-tools": shot_menu_tools,
    "menu-view": shot_menu_view,
    "main-popup": shot_main_popup,
    "reading": shot_reading,
    "about": shot_about,
    "options": shot_options,
    "chapter": shot_chapter,
    "review": shot_review,
}


def main() -> int:
    names = sys.argv[1:] or list(SHOTS)

    # 每张图一个独立进程：互不污染，且某张卡住不影响其余
    if os.environ.get("TF_SHOT_CHILD") != "1":
        import subprocess
        env = dict(os.environ, TF_SHOT_CHILD="1")
        failed = []
        for name in names:
            print(f"[{name}]", flush=True)
            rc = subprocess.call([sys.executable, "-u", os.path.abspath(__file__), name],
                                 env=env)
            if rc != 0:
                failed.append(name)
        print("完成。" if not failed else f"失败：{failed}")
        return 1 if failed else 0

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))

    os.makedirs(OUT_DIR, exist_ok=True)
    name = names[0]
    fn = SHOTS.get(name)
    if fn is None:
        print(f"  [跳过] 未知的截图名：{name}")
        return 0
    fn(app)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())