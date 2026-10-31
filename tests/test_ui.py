"""界面层冒烟测试：驱动主窗口完成一次真实的“打开 → 整理 → 替换 → 保存”流程。

运行：``QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe tests/test_ui.py``
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt                      # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel         # noqa: E402

from app.core import encoding as enc                       # noqa: E402
from app.core.settings import Settings                     # noqa: E402
from app.ui import dialogs, icons                          # noqa: E402
from app.ui.main_window import MainWindow                  # noqa: E402
from app.ui.task import task_running                       # noqa: E402
from app.ui.widgets import Menu                            # noqa: E402

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

    def wait_bg(owner, timeout: float = 15.0) -> None:
        """等后台任务跑完并处理回调（整理/审核都改成异步了，测试要显式等）。"""
        deadline = time.monotonic() + timeout
        while task_running(owner) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        for _ in range(5):        # 让排队的 done 信号送达
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
    wait_bg(window)
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
    wait_bg(review)
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

    # ---- 自绘菜单弹层的黑角防护（回归点 ×2：① DWM 投影 + 透明弹层冲突，
    # 圆角外渲染成纯黑；② DPR 除不尽时窗口最后一行物理像素只被逻辑绘制覆盖
    # 一半，半透明像素被 DWM 混成底边一条暗线 —— 所以弹层必须完全不透明）
    from PySide6.QtCore import Qt as _Qt
    from app.ui.widgets import Menu as _Menu
    _m = _Menu()
    check("菜单弹层完全不透明（无 WA_TranslucentBackground）",
          not _m.testAttribute(_Qt.WidgetAttribute.WA_TranslucentBackground))
    _pal = _m.palette().color(_m.backgroundRole())
    check("菜单弹层底色 = 卡片白", _pal.name().upper() == "#FFFFFF", _pal.name())
    check("菜单弹层无系统投影",
          bool(_m.windowFlags() & _Qt.WindowType.NoDropShadowWindowHint))
    _m.resize(120, 80)
    _m.apply_round_mask()        # mask 逻辑抽成方法：不依赖真实弹窗即可断言
    # 圆角外黑点防护是两级：像素级 alpha=0 在 Qt 6.12 弹层上不可靠（alpha<255
    # 会被 DWM 混成黑色，实测圆角边出现黑点），现在是把弹层画实 + 系统级
    # setMask 裁掉圆角外。断言查 mask 本身：四个角必须在 mask 之外，
    # 主体必须在内 —— mask 外不存在像素，无论 DWM 怎么合成都出不了黑。
    # 同时防「mask 是空的」假通过：空 region 的 contains 恒 False，
    # corners_out 会全 True，所以 body_in 必须一起断言。
    _mask = _m.mask()
    w, h = _m.width(), _m.height()
    corners_out = [not _mask.contains(QPoint(x, y))
                   for x, y in ((1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2))]
    body_in = all(_mask.contains(QPoint(x, y))
                  for x, y in ((w // 2, h // 2), (5, h // 2), (w // 2, 5)))
    check("菜单圆角被 mask 裁掉（系统级）", all(corners_out) and body_in,
          f"corners_out={corners_out} body_in={body_in}")
    _m.close()
    _m.deleteLater()

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
    # 复制入口只有邮箱胶囊一个（ComicConverter 同款：按钮栏只留「关闭」）
    about.chip.copy()
    check("关于页复制邮箱", QApplication.clipboard().text() == AUTHOR_EMAIL)
    check("关于页胶囊文字不变", about.chip._label.text() == AUTHOR_EMAIL, about.chip._label.text())
    check("关于页右侧提示已复制", about.hint.text() == "已复制到剪贴板", about.hint.text())
    check("关于页无独立复制按钮",
          not any(btn.text() == "复制邮箱" for btn in about.findChildren(dialogs.QPushButton)))
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

    # ---- 缩小窗口不能出现错乱：按钮不被压扁、列表不被裁
    # 回归点：① 命令栏按钮被 Qt 压到宽度不足 → 文字被裁成「一键审」；
    #          ② 右侧正则列表高度写死 → 撑破面板、盖住下方说明文字；
    #          ③ 缩小收起文字后放大 → 文字必须放回来（收起集要跨调用保持）。
    def bar_texts() -> list[str]:
        return window.visible_command_labels()

    # 1700 宽时命令栏能放下全部文字；先在宽窗口取基准，缩小收起、
    # 再放大必须恢复。收不收字现在完全由按钮的实际宽度决定（按钮自己在
    # resizeEvent 里判断），没有"已收起"集合那种可卡的中间态。
    window.resize(1700, 880)
    app.processEvents()
    full_texts = bar_texts()
    for w, h in ((1160, 720), (1420, 880), (1160, 720), (1420, 880)):
        window.resize(w, h)
        app.processEvents()
        squeezed = [b.text() for b in window.command_buttons
                    if b.text() and b.geometry().width() < b.natural_width() - 2]
        check(f"{w}x{h} 命令栏按钮未被压扁", not squeezed, str(squeezed))
        rp = window.replace_panel
        lib = rp.library
        check(f"{w}x{h} 正则列表未溢出面板",
              lib.geometry().bottom() <= rp.height(),
              f"列表底 {lib.geometry().bottom()} / 面板高 {rp.height()}")
        check(f"{w}x{h} 正则列表高度是行高整数倍",
              (lib.height() - 8) % rp._row_height == 0, str(lib.height()))
    window.resize(1700, 880)
    app.processEvents()
    check("缩小再放大文字全部恢复", bar_texts() == full_texts,
          f"{full_texts} -> {bar_texts()}")

    # ---- 还原为打开时的内容（保存过也能还原）
    window.editor.setPlainText("被改坏的内容")
    app.processEvents()
    check("改动后可还原", window.act_revert.isEnabled())
    window._do_revert()
    app.processEvents()
    check("还原生效", window.editor.toPlainText() == window._original_text)
    check("还原后与磁盘不同则标记修改", window.modified)
    window.modified = False        # 避免关闭时弹“是否保存”阻塞测试

    # ---- 弹层位置固定（规范：下拉框位置与当前选中项无关）
    # 必须在窗口还开着时测 —— 窗口关掉后下拉框不可见，锚点算不出来。
    combo = window.convert_combo
    geoms = []
    for idx in (0, 3, 7, 1):
        combo.setCurrentIndex(idx)
        app.processEvents()
        combo.showPopup()
        app.processEvents()
        w = combo.view().window()
        geoms.append((w.x(), w.y(), w.width(), w.height()))
        combo.hidePopup()
        app.processEvents()
    check("下拉弹层位置与选中项无关", len(set(geoms)) == 1, str(set(geoms)))

    # ---- 下拉弹层样式：圆角 mask + 条目内缩（回归点：方角列表盖住容器圆角，
    #      选中项通到边上，整个弹层看着像套了两层框）
    combo.showPopup()
    app.processEvents()
    popup = combo.view().window()
    region = popup.mask()
    check("下拉弹层有圆角 mask", not region.isEmpty()
          and not region.contains(QPoint(popup.rect().left(), popup.rect().top())),
          str(region.boundingRect()))
    combo.hidePopup()
    app.processEvents()

    # ---- 无图标菜单不保留图标列（回归点：简繁菜单两项纯文字，文字却按
    #      图标列缩进 48px，左边一大块空白）
    from PySide6.QtGui import QPixmap
    plain_menu = Menu()
    plain_menu.addAction("繁转简")
    plain_menu.addAction("简转繁")
    shot = QPixmap(160, 80)
    shot.fill(Qt.GlobalColor.white)
    plain_menu.render(shot, QPoint(0, 0))
    check("无图标菜单不留图标列", getattr(plain_menu, "_has_icon_col", True) is False)
    icon_menu = Menu()
    icon_menu.addAction(icons.icon("open"), "打开")
    icon_menu.addAction("纯文字项")
    shot2 = QPixmap(200, 90)
    shot2.fill(Qt.GlobalColor.white)
    icon_menu.render(shot2, QPoint(0, 0))
    check("有图标菜单仍对齐图标列", getattr(icon_menu, "_has_icon_col", True) is True)

    # ---- 右栏：标题与第一个控件贴紧（回归点：标题与下面的框间隔过大）
    rp = window.replace_panel
    title_labels = [w for w in rp.findChildren(QLabel)
                    if w.property("role") == "title"]
    check("替换规则标题存在", any(w.text() == "替换规则" for w in title_labels),
          str([w.text() for w in title_labels]))
    first_title = min(title_labels, key=lambda w: w.y())
    gap = rp.find_edit.geometry().top() - first_title.geometry().bottom()
    check("标题紧贴查找框", 0 <= gap <= 8, str(gap))

    # ---- 自动化面板
    panel = window.automation_panel
    check("自动化面板存在", panel is not None and panel.isVisible())
    # 空态用全新 Settings 验证（dev 的 config.json 可能残留上一轮测试的任务）
    from app.ui.automation import AutomationPanel as _AutoPanel
    fresh = _AutoPanel(Settings())
    check("自动化初始无任务时运行禁用", not fresh.btn_run.isEnabled()
          and fresh.combo.count() == 0)
    fresh.deleteLater()
    check("自动化运行按钮状态与任务数一致",
          panel.btn_run.isEnabled() == (panel.combo.count() > 0))

    task = {
        "name": "测试任务",
        "steps": [
            {"type": "rstrip", "config": {}},
            {"type": "replace", "config": {"pattern": "必竟", "replacement": "归根结底",
                                           "use_regex": False, "ignore_case": False}},
        ],
    }
    # 前面的还原测试把正文恢复成了打开时的原文；另外测试前段把 window.settings
    # 换成了新实例，面板持有的是原实例 —— 任务登记到面板持有的那份上再执行
    panel.settings.automations.append(task)
    panel.refresh()
    punct_before = window.settings.punct_mode
    window.run_automation(task)
    wait_bg(window)
    text = window.editor.toPlainText()
    check("自动化-替换生效", "归根结底" in text, text[:60])
    check("自动化-记录上次调用", window.settings.last_automation == "测试任务",
          window.settings.last_automation)
    check("自动化-不改动程序配置", window.settings.punct_mode == punct_before,
          window.settings.punct_mode)
    check("自动化-面板出现任务", panel.combo.count() == 1
          and panel.combo.currentText() == "测试任务")

    # 空任务 / 空文档直接提示，不崩
    window.run_automation({"name": "空任务", "steps": []})
    window.editor.setPlainText("")
    window.run_automation(task)
    app.processEvents()
    check("自动化-空文档安全", True)

    # 任务编辑器：不 exec，直接驱动保存路径
    from app.ui.automation import AutomationDialog
    dlg = AutomationDialog(window, None, ["测试任务"])
    dlg.name_edit.setText("测试任务")
    dlg._steps = list(task["steps"])
    dlg.accept()
    check("编辑器-重名拒绝", dlg.result_task is None and dlg._notice.text() != "")
    dlg.name_edit.setText("另一个任务")
    dlg.accept()
    check("编辑器-保存成功", dlg.result_task is not None
          and dlg.result_task["name"] == "另一个任务")
    dlg2 = AutomationDialog(window, task, [])
    check("编辑器-编辑回填", dlg2.name_edit.text() == "测试任务"
          and len(dlg2._steps) == 2)

    # ---- 内联确认条（规范 §七 ③）：不可逆操作不弹模态框
    window.editor.setPlainText("改了内容")
    app.processEvents()
    check("内容已改动", window.editor.toPlainText() != window._original_text)
    window.revert_to_original()
    app.processEvents()
    check("还原走内联确认条", window.confirm_bar.isVisible())
    check("确认条不在弹窗上", not window.confirm_bar.isModal())
    # 危险确认的主按钮必须是红色语义色（回归点：kind 属性改了但没 repolish，
    # 主按钮一直是强调绿 —— 危险链路整条是断的）
    check("危险确认主按钮是 danger 样式",
          window.confirm_bar._ok.property("kind") == "danger",
          str(window.confirm_bar._ok.property("kind")))
    before = window.editor.toPlainText()
    window._on_confirm_bar_ok()
    app.processEvents()
    check("确认后确认条收起", not window.confirm_bar.isVisible())
    check("确认后已执行还原", window.editor.toPlainText() != before)
    # 非危险确认要切回普通主按钮
    window._ask_confirm("普通确认", "继续", lambda: None, danger=False)
    app.processEvents()
    check("普通确认主按钮回到 primary",
          window.confirm_bar._ok.property("kind") == "primary",
          str(window.confirm_bar._ok.property("kind")))
    window._on_confirm_bar_cancel()

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
