"""界面层冒烟测试：驱动主窗口完成一次真实的“打开 → 整理 → 替换 → 保存”流程。

运行：``QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe tests/test_ui.py``
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication               # noqa: E402

from app.core import encoding as enc                     # noqa: E402
from app.core.settings import Settings                   # noqa: E402
from app.ui import dialogs                               # noqa: E402
from app.ui.main_window import MainWindow                # noqa: E402

RAW = """第1章 开端

　　他慢慢的说,这件事很奇怪。第二天早上,他醒了过来,发现自己躺在床上,身上盖着被子,窗外阳光明媚,鸟语花香,一切看起来都很正常,但是他心里总觉得有什么地方不太对劲,于是起身走到窗前
　　向外望去。

16K小说网 更新时间:2010-3-4 13:02:57 本章字数:4143

　　少*妇站在门口,手里端着一碗热汤。

第2章 发展

　　接下来的几天,他一直在思考这个问题。必竟这件事关系到所有人,按纳不住心中的疑惑。
"""

PASS = 0
FAIL = 0
NOTES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        NOTES.append(f"{name} {extra}")


def main() -> int:
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")

    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "样例.txt")
    enc.save_text(path, RAW, "gb18030", "\r\n")

    window = MainWindow()
    window.resize(1280, 820)
    window.show()
    app.processEvents()

    # ---- 打开
    window.open_path(path)
    app.processEvents()
    check("打开后内容一致", window.editor.toPlainText() == RAW)
    check("识别编码", window.encoding == "gb18030", window.encoding)
    check("识别行尾", window.newline == "\r\n", repr(window.newline))
    check("标题显示文件名", "样例.txt" in window.windowTitle(), window.windowTitle())
    check("文件加入列表", path in window.file_panel.paths())

    # ---- 格式整理
    settings = Settings()
    settings.para_spacing = "keep"
    settings.indent_kind = "full"
    settings.indent_count = 2
    window.settings = settings
    window.run_format()
    app.processEvents()
    text = window.editor.toPlainText()
    check("标点转全角", "，" in text, text[:40])
    check("广告行被删除", "16K小说网" not in text)
    check("屏蔽码被还原", "少妇站在门口" in text)
    check("硬回车合并", "于是起身走到窗前向外望去" in text)
    check("行首缩进", "　　他慢慢的说" in text)
    check("文档标记为已修改", window.modified)

    # ---- 查找
    window.replace_panel.find_edit.setText("第[0-9]+章")
    window.find_next(True)
    app.processEvents()
    check("查找命中", len(window._matches) == 2, str(len(window._matches)))
    check("选中第一处", window.editor.textCursor().selectedText() == "第1章",
          window.editor.textCursor().selectedText())
    window.find_next(True)
    check("查找下一个", window.editor.textCursor().selectedText() == "第2章",
          window.editor.textCursor().selectedText())
    window.find_next(False)
    check("查找上一个", window.editor.textCursor().selectedText() == "第1章",
          window.editor.textCursor().selectedText())

    # ---- 替换
    window.replace_panel.find_edit.setText("必竟")
    window.replace_panel.repl_edit.setText("毕竟")
    window.replace_all(False)
    app.processEvents()
    check("替换生效", "毕竟" in window.editor.toPlainText())

    # ---- 简单文本查找（非正则）
    window.replace_panel.regex_check.setChecked(False)
    window.replace_panel.find_edit.setText("按纳")
    window.find_next(True)
    check("字面查找", len(window._matches) >= 1, str(len(window._matches)))
    window.replace_panel.regex_check.setChecked(True)

    # ---- 保存（覆盖确认对话框在测试里跳过：直接标记为已确认）
    check("打开后未确认覆盖", window._save_confirmed is False)
    window._save_confirmed = True
    window.save_file()
    app.processEvents()
    raw = open(path, "rb").read()
    check("保存保持 CRLF", raw.count(b"\n") == raw.count(b"\r\n") and raw.count(b"\r\n") > 5,
          f"lf={raw.count(b'\n')} crlf={raw.count(b'\r\n')}")
    doc = enc.read_text(path)
    check("保存保持 GBK", doc.encoding == "gb18030", doc.encoding)
    check("保存后未修改", not window.modified)
    check("保存内容正确", "毕竟" in doc.text and "16K小说网" not in doc.text)

    # ---- 章节对话框
    dialog = dialogs.SplitDialog(window.editor.toPlainText(), settings, window)
    dialog.reload_chapters()
    check("章节识别", len(dialog.chapters) == 2, str(len(dialog.chapters)))
    dialog.out_edit.setText(tmp)
    dialog.prefix_edit.setText("测试")
    dialog._do_split()
    check("分割参数", dialog.split_requested is not None)
    dialog.close()

    # ---- 快速审核
    review = dialogs.QuickReviewDialog(window.editor.toPlainText(), window)
    review._run()
    check("审核有结果", len(review._all) > 0, str(len(review._all)))
    review.close()

    # ---- 视图切换不崩溃
    window.toggle_reading_mode(True)
    window.toggle_guide(True)
    window.toggle_auto_scroll(True)
    window.toggle_auto_scroll(False)
    window.toggle_wrap(False)
    window.toggle_wrap(True)
    window.toggle_reading_mode(False)
    app.processEvents()
    check("视图切换正常", True)

    # ---- 联系方式（点击复制，不打开外部程序）
    from app.core.version import AUTHOR_EMAIL
    QApplication.clipboard().setText("")
    window.copy_contact()
    check("菜单复制邮箱", QApplication.clipboard().text() == AUTHOR_EMAIL,
          QApplication.clipboard().text())
    check("状态栏不含邮箱",
          all("@" not in lbl.text()
              for lbl in window.statusBar().findChildren(dialogs.QLabel)))
    about = dialogs.AboutDialog(window)
    QApplication.clipboard().setText("")
    about._copy()
    check("关于页复制邮箱", QApplication.clipboard().text() == AUTHOR_EMAIL)
    check("关于页文案不随复制变化", about.hint.text() == "点击即可复制", about.hint.text())
    check("关于页胶囊文字不变", about.chip._label.text() == AUTHOR_EMAIL, about.chip._label.text())
    check("关于页不打开外链", not about.findChild(dialogs.QTextBrowser).openExternalLinks())
    about.close()

    # ---- 阅读模式：隐藏行号、改成居中的窄栏
    window.apply_reading_mode(True)
    app.processEvents()
    check("阅读模式已开启", window.editor.reading_mode and window.mode_btn.isChecked())
    check("阅读模式隐藏行号", not window.editor._line_area.isVisible())
    check("阅读模式左右留白", window.editor.viewportMargins().left() > 20,
          str(window.editor.viewportMargins().left()))
    check("菜单同步阅读模式", window.act_reading.isChecked())
    window.apply_reading_mode(False)
    app.processEvents()
    check("回到整理模式", not window.editor.reading_mode and window.mode_btn.isChecked() is False)
    check("整理模式恢复行号", window.editor._line_area.isVisible())

    # ---- 还原为打开时的内容（保存过也能还原）
    window.editor.setPlainText("被改坏的内容")
    app.processEvents()
    check("改动后可还原", window.act_revert.isEnabled())
    window._do_revert()
    app.processEvents()
    check("还原生效", window.editor.toPlainText() == window._original_text)
    check("还原后与磁盘不同则标记修改", window.modified)
    window.modified = False        # 避免关闭时弹“是否保存”阻塞测试
    window.close()
    print(f"\n通过 {PASS} 项，失败 {FAIL} 项")
    if NOTES:
        print("失败详情：")
        for n in NOTES:
            print(" -", n)
        return 1
    print("界面冒烟测试通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
