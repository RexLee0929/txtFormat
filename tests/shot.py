"""离屏渲染截图，用于检查界面外观。

用法：``.venv/Scripts/python.exe tests/shot.py out.png [窗口宽] [窗口高]``
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QFont                       # noqa: E402
from PySide6.QtWidgets import QApplication            # noqa: E402

from app.ui.main_window import MainWindow             # noqa: E402

SAMPLE = """第1章 开端

　　他慢慢的说,这件事很奇怪。第二天早上,他醒了过来,发现自己躺在床上,身上盖着被子,窗外阳光明媚,鸟语花香,一切看起来都很正常,但是他心里总觉得有什么地方不太对劲。

　　“你醒了?”一个声音从门口传来。

　　少*妇站在门口,手里端着一碗热汤。

16K小说网 更新时间:2010-3-4 13:02:57 本章字数:4143

第2章 发展

　　接下来的几天,他一直在思考这个问题。必竟这件事关系到所有人,按纳不住心中的疑惑,他决定去找老张问个明白。
"""


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "shot.png"
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 1420
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 880

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))

    window = MainWindow()
    window.resize(width, height)
    window._set_text(SAMPLE, None)
    window.show()
    app.processEvents()

    # 用示例文件填充左侧列表
    sample_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
    os.makedirs(sample_dir, exist_ok=True)
    for name in ("都市少帅 第01卷.txt", "都市少帅 第02卷.txt"):
        path = os.path.join(sample_dir, name)
        if not os.path.exists(path):
            open(path, "w", encoding="utf-8").write(SAMPLE)
    window.file_panel.load_directory(sample_dir)
    app.processEvents()

    pixmap = window.grab()
    pixmap.save(out)
    print("saved", out, pixmap.width(), pixmap.height())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
