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
from PySide6.QtWidgets import (QApplication, QFrame, QLabel,  # noqa: E402
                               QWidget)

from app.core import encoding as enc                       # noqa: E402
from app.core.settings import Settings                     # noqa: E402
from app.ui import dialogs, icons                          # noqa: E402
from app.ui.theme import Color                             # noqa: E402
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
    # 主题挂 QApplication 全局（与 main.main 同口径）—— 主窗口自己不再设
    # 基础主题，测试里不挂全局的话所有控件都会退回原生外观
    from app.ui.theme import stylesheet as _theme_stylesheet
    app.setStyleSheet(_theme_stylesheet())

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
    # 上下滚动提示箭头（回归点：列表超过显示行数时 Qt 会插两条灰色
    # QComboBoxPrivateScroller 横带，用户报「太丑」；滚动交给右侧滚动条）。
    # offscreen 平台 Qt 不产生 scroller，这里恒真 —— 真实平台的强断言在
    # selftest.popuptest（exe 自检走真实窗口）。
    scrollers = [c for c in popup.findChildren(QWidget)
                 if c.metaObject().className() == "QComboBoxPrivateScroller"]
    check("下拉弹层无滚动提示箭头", not any(s.isVisible() for s in scrollers),
          str([(s.isVisible(), s.height()) for s in scrollers]))
    combo.hidePopup()
    app.processEvents()

    # 弹层宽度 = 字段宽度（严格同宽，回归点：旧实现取 max(字段宽, 最宽项)，
    # 用户字体/缩放下最宽项比字段宽 → 弹层超出压到旁边控件）。
    # 视图比弹层窄 2px 是设计使然：容器左右各 1px 布局边距把边框从窗口
    # 边缘内收（贴边画会被 DWM 栅格化吃掉，见 CompactComboBox 注释）。
    combo.setFixedWidth(120)
    long_combo = combo
    long_combo.addItem("一条特别特别特别特别特别特别长的条目文字")
    long_combo.setCurrentIndex(long_combo.count() - 1)
    app.processEvents()
    long_combo.showPopup()
    app.processEvents()
    app.processEvents()
    check("下拉弹层与字段严格同宽",
          long_combo.view().window().width() == long_combo.width()
          and long_combo.view().width() == long_combo.width() - 2,
          f"popup {long_combo.view().window().width()} / view {long_combo.view().width()} / field {long_combo.width()}")
    long_combo.hidePopup()
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

    # ---- 菜单图标与文字的光学对齐（回归点：①高 DPR 屏把 pixmap 的设备像素
    #      当逻辑像素参与居中，图标左偏 3px、上偏 ~9px；②雅黑的 descent 对
    #      纯中文菜单项是空的，按条目矩形几何居中会让图标比文字低 1.5~2px。
    #      修复后图标/勾的墨迹中心应与文字墨迹中心差 ≤1.5px）
    from PySide6.QtGui import QImage as _QImage
    align_menu = Menu()
    for _n in ("new", "open", "save", "folder", "close"):
        align_menu.addAction(icons.icon(_n), "菜单项文字")
    align_menu.resize(align_menu.sizeHint())
    mimg = _QImage(align_menu.size(), _QImage.Format.Format_RGB32)
    mimg.fill(Qt.GlobalColor.white)
    align_menu.render(mimg)

    def _ink_rows(x0, x1, y0, y1):
        rows = []
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                c = mimg.pixelColor(xx, yy)
                if c.alpha() > 30 and c.red() + c.green() + c.blue() < 600:
                    rows.append(yy)
                    break
        return rows

    worst = 0.0
    for _act in align_menu.actions():
        if _act.isSeparator() or not _act.isVisible() or _act.icon().isNull():
            continue
        _g = align_menu.actionGeometry(_act)
        _irows = _ink_rows(_g.x() + 11, _g.x() + 33, _g.y(), _g.y() + _g.height())
        _trows = _ink_rows(_g.x() + 42, _g.x() + _g.width() - 6, _g.y(), _g.y() + _g.height())
        if not _irows or not _trows:
            worst = 99.0
            break
        worst = max(worst, abs((min(_irows) + max(_irows)) / 2
                               - (min(_trows) + max(_trows)) / 2))
    check("菜单图标与文字光学对齐", worst <= 1.5, f"最大偏差 {worst:.1f}px")

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

    # ---- 菜单数据驱动 + §十 四断言
    from app.ui import menu_def
    bar = window.menuBar().actions()
    check("菜单-一级菜单≥2栏", len(bar) >= 2, str(len(bar)))
    check("菜单-每栏非空且至少一项可用",
          all(a.menu() is not None and any(x.isEnabled() and not x.isSeparator()
                                           for x in a.menu().actions()) for a in bar))
    help_act = next((a for a in bar if a.text().replace("&", "").startswith("帮助")), None)
    check("菜单-存在帮助栏", help_act is not None)
    check("菜单-帮助里有 about 命令",
          bool(help_act and any(x.data() == menu_def.ABOUT_CMD
                                for x in help_act.menu().actions())))
    check("菜单-数据表里也有 about 命令",
          any(i.cmd == menu_def.ABOUT_CMD for i in menu_def.all_items()))
    # 数据表 → 建树没漏项：每栏的命令条数一致（分隔线不计）
    def data_count(group) -> int:
        total = 0
        for item in group.items:
            if item.submenu:
                total += len(item.submenu)
            elif item.text != "-":
                total += 1
        return total

    check("菜单-建树条数与数据表一致",
          all(len([x for x in a.menu().actions() if not x.isSeparator()])
              == sum(1 for it in g.items if it.text != "-") for a, g in zip(bar, menu_def.MENUS)
              ),
          str([len([x for x in a.menu().actions() if not x.isSeparator()]) for a in bar]))
    # 分发器不认识的命令 id 会让菜单项变哑巴 —— 逐个核对
    table = window._command_table()
    unknown = sorted({it.cmd for it in menu_def.all_items()
                      if it.cmd and it.cmd not in table})
    check("菜单-命令 id 全部有处理函数", not unknown, str(unknown))

    # ---- 对话框主按钮文案（规范 §七.3：主按钮是动词短语，不写「确定」）
    # 三道防回归：① add_footer 的 ok_text 不再有默认值（漏传直接 TypeError）；
    # ② 现有调用点全部显式传了词；③ 传的词不是「确定/确认/OK」这类无信息量的。
    import inspect
    import re as _re
    sig = inspect.signature(dialogs.BaseDialog.add_footer).parameters["ok_text"]
    check("对话框-主按钮文案必填（防止默认「确定」被顺手带进来）",
          sig.default is inspect.Parameter.empty, repr(sig.default))
    weak = {"确定", "确认", "OK", "ok", "是", "好", ""}
    offenders: list[str] = []
    ui_dir = os.path.join("app", "ui")
    for name in sorted(os.listdir(ui_dir)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(ui_dir, name), encoding="utf-8") as fh:
            src = fh.read()
        for m in _re.finditer(r"add_footer\(\s*([^)]*)\)", src):
            first = m.group(1).split(",")[0].strip().strip("\"'")
            if first == "self":                    # 定义本身，跳过
                continue
            if first in weak:
                offenders.append(f"{name}: {m.group(1).strip()[:24]}")
    check("对话框-主按钮都是动词短语", not offenders, str(offenders))

    # ---- 对话框宽度：按内容算（规范 §七.2，审计 §10.4 的三条判据）
    import inspect
    sig_params = inspect.signature(dialogs.BaseDialog.__init__).parameters
    check("对话框-构造参数里没有宽度死数", "width" not in sig_params, str(list(sig_params)))

    from app.ui.errdialog import ErrorDialog
    e_short = ErrorDialog("短。", "")
    e_long = ErrorDialog("分割文件时目标目录不可写，可能被其他程序占用，或当前账户没有该目录的写入权限。", "")
    for d in (e_short, e_long):
        d.show()
    app.processEvents()
    check("对话框-改文案宽度跟着变（判据③）", e_long.width() > e_short.width(),
          f"{e_short.width()} → {e_long.width()}")
    check("对话框-宽度落在 [MIN, WRAP_LIMIT]",
          all(dialogs.MIN_WIDTH <= d.width() <= dialogs.WRAP_LIMIT
              for d in (e_short, e_long)),
          f"{e_short.width()} / {e_long.width()}")
    for d in (e_short, e_long):
        d.close()

    g = dialogs.GotoDialog(10)
    o = dialogs.OptionsDialog(window.settings)
    for d in (g, o):
        d.show()
    app.processEvents()
    check("对话框-不同框宽度不同（判据②）", g.width() != o.width(),
          f"转到 {g.width()} vs 选项 {o.width()}")
    check("对话框-NoResize（min == max）",
          all(d.minimumWidth() == d.maximumWidth() for d in (g, o)),
          f"{g.minimumWidth()} / {o.minimumWidth()}")
    for d in (g, o):
        d.close()

    # 工具窗口（§七.7）：可拉伸、宽度归用户 —— 曾经被 BaseDialog 的 setFixedSize 一并钉死
    tool = dialogs.QuickReviewDialog("第1章 开端\n\n　　正文一句。")
    tool.show()
    app.processEvents()
    check("工具窗口-可拉伸（min < max）", tool.minimumWidth() < tool.maximumWidth(),
          f"{tool.minimumWidth()} / {tool.maximumWidth()}")
    before_w = tool.width()
    tool.resize(before_w + 220, tool.height())
    app.processEvents()
    check("工具窗口-真的能拉宽", tool.width() > before_w, f"{before_w} → {tool.width()}")
    tool.close()

    # ---- 错误框（规范 §七.4 / §七.2）
    from app.ui.errdialog import ErrorDialog
    from app.core.version import APP_NAME
    err = ErrorDialog("测试错误信息", "")
    err.show()
    app.processEvents()
    check("错误框-窗口标题只写程序名", err.windowTitle() == APP_NAME, err.windowTitle())
    check("错误框-不可拉伸", err.minimumWidth() == err.maximumWidth()
          and err.minimumHeight() == err.maximumHeight(),
          f"{err.minimumWidth()}/{err.maximumWidth()}")
    labels = [w.text() for w in err.findChildren(QLabel)]
    check("错误框-标题说事不写「错误/提示」",
          any("没有完成" in t for t in labels) and not any(t in ("错误", "提示") for t in labels),
          str(labels[:3]))
    # 回归点：QLabel 竖直 Preferred 会被布局拉高，标题行曾撑到 44px（多出一条空带）
    head_label = next(w for w in err.findChildren(QLabel) if "没有完成" in w.text())
    check("错误框-标题行未被拉高", head_label.height() <= 26, str(head_label.height()))

    # 版式要点（四轮返工的结论）：图标只在标题行占位（规范 §七「错误框 24」），
    # 正文列缩进到标题文字下方 —— 整块两条左缘，不是三条。
    mark = next((w for w in err.findChildren(QLabel)
                 if w.pixmap() is not None and not w.pixmap().isNull()), None)
    check("错误框-标题行左侧有 24px 图标",
          mark is not None and (mark.width(), mark.height()) == (24, 24),
          "" if mark is None else f"{mark.width()}×{mark.height()}")
    if mark is not None:
        img = mark.pixmap().toImage()
        want = tuple(int(Color.danger[i:i + 2], 16) for i in (1, 3, 5))
        near = False
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                if c.alpha() > 200 and sum((a - b) ** 2 for a, b in
                                          zip((c.red(), c.green(), c.blue()), want)) < 400:
                    near = True
                    break
            if near:
                break
        # 图标与标题必须同源同色（规范 §四.1）：文字用 Color.danger，图标也用
        check("错误框-图标就是 Color.danger（不与标题撞成两个红）", near)
    body_label = next(w for w in err.findChildren(QLabel) if w.text() == "测试错误信息")
    pos_mark = mark.mapTo(err, mark.rect().topLeft()) if mark is not None else None
    pos_head = head_label.mapTo(err, head_label.rect().topLeft())
    pos_body = body_label.mapTo(err, body_label.rect().topLeft())
    body_indent = body_label.contentsMargins().left()
    check("错误框-正文与标题文字同左缘",
          pos_body.x() + body_indent == pos_head.x(),
          f"{pos_body.x()}+{body_indent} vs {pos_head.x()}")
    check("错误框-图标贴左边距、与标题留 8px 以上",
          pos_mark is not None and pos_mark.x() == 20
          and pos_mark.x() + mark.width() + 8 <= pos_head.x(),
          "" if pos_mark is None else f"{pos_mark.x()} → {pos_head.x()}")
    check("错误框-不套卡片（不留多余左缘）",
          err.findChild(QFrame, "ErrorCard") is None)
    err.close()
    # 错误框必须跟着主窗（没有 parent 时 QDialog 会弹到屏幕正中，主窗在副屏就跑到另一块屏）
    err_child = ErrorDialog("测试错误信息", "", window)
    check("错误框-挂在主窗上（有 parent）", err_child.parent() is window)
    err_child.close()

    # ---- 状态栏：固定 26px、底色比窗口深一档（规范 §六「状态栏是仪表」）
    from app.ui import theme as theme_mod
    def _lum(hex_color: str) -> int:
        return sum(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    bar = window.statusBar()
    check("状态栏-固定 26px", bar.height() == 26, str(bar.height()))
    check("状态栏-底色比窗口底色深一档",
          _lum(theme_mod.Color.status_bg) < _lum(theme_mod.Color.window)
          and theme_mod.Color.status_bg.upper() != theme_mod.Color.window.upper(),
          f"{theme_mod.Color.status_bg} vs {theme_mod.Color.window}")

    # ---- 主按钮悬停不变色（规范 §八）
    # 不用「模拟悬停再取像素」：offscreen 平台下 WA_UnderMouse 不会让 QSS :hover 生效
    # （实测普通按钮也不变色），那样写的断言永远为真 —— 等于没测。改为直接读样式表。
    import re as _re2
    css = theme_mod.stylesheet()
    m = _re2.search(r'QPushButton\[kind="primary"\]:hover\s*\{\s*background:\s*([^;]+);', css)
    check("主按钮-悬停底色就是强调色（不变色）",
          m is not None and m.group(1).strip().upper() == theme_mod.ACCENT.upper(),
          "" if m is None else m.group(1).strip())
    # TF-6：不再导出用不到的强调色（留着会让人以为界面上真用到了）
    for dead in ("ACCENT_HOVER", "ACCENT_DARK", "ACCENT_HOVER_BG"):
        check(f"主题-不残留未使用的 {dead}", not hasattr(theme_mod, dead), str(getattr(theme_mod, dead, "")))

    # ---- 单实例名按程序目录区分（安装版 / 绿色版不能互相抢）
    from app import main as main_mod
    check("单实例-名字带程序目录散列",
          _re2.search(r"-[0-9a-f]{8}$", main_mod._INSTANCE_KEY) is not None,
          main_mod._INSTANCE_KEY)
    # 状态栏红字通道
    window.show_error_status("出错，详见 error.log")
    app.processEvents()
    check("状态栏红字-可见且为警示色",
          window.err_label.isVisible() and "C42B1C" in window.err_label.styleSheet().upper(),
          window.err_label.styleSheet())

    # ---- 自绘字体对话框
    from app.core import settings as _settings_mod
    from app.ui.fontdialog import DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE, FontDialog
    # 默认值单源：对话框的「恢复默认值」必须引用 Settings 的实际默认，
    # 不许再写第二份（回归点：曾写死「黑体 14」，与实际默认雅黑 UI 12 对不上）
    check("字体对话框-默认值与 Settings 同源",
          DEFAULT_FONT_FAMILY == _settings_mod.Settings.font_family
          and DEFAULT_FONT_SIZE == _settings_mod.Settings.font_size,
          f"{DEFAULT_FONT_FAMILY}/{DEFAULT_FONT_SIZE}")
    _def_family = _settings_mod.Settings.font_family
    _def_size = _settings_mod.Settings.font_size
    fdlg = FontDialog("Microsoft YaHei UI", 12)
    fdlg.show()
    app.processEvents()

    def _pt(label) -> float:
        """读控件字号的显示值（pt）。show 之后 Qt 会把 pt 解析成 px，用像素反算。"""
        f = label.font()
        return f.pointSize() if f.pointSize() > 0 else \
            round(f.pixelSize() * 72.0 / app.primaryScreen().logicalDotsPerInch())

    check("字体对话框-不可拉伸", fdlg.minimumWidth() == fdlg.maximumWidth())
    check("字体对话框-预览跟随字号", _pt(fdlg.preview) == 12, str(_pt(fdlg.preview)))
    # 预览必须跟随所选字体（回归点：主题里的 `* { font-family }` 会盖掉
    # setFont，之前预览永远显示全局雅黑 → 用户报「实际展示没有任何变化」。
    # 预览只能走样式表；离屏环境字体库为空，这里就断言"样式表驱动"这条机制。）
    check("字体对话框-预览字体由样式表驱动",
          'font-family: "Microsoft YaHei UI"' in fdlg.preview.styleSheet(),
          fdlg.preview.styleSheet()[:60])
    _other = next((fdlg.font_list.item(i).text() for i in range(fdlg.font_list.count())
                   if fdlg.font_list.item(i).text() != "Microsoft YaHei UI"), "")
    if _other:
        fdlg._select(_other)
        app.processEvents()
        check("字体对话框-预览跟随所选字体",
              _other in fdlg.preview.styleSheet()
              and fdlg.preview.font().family() == _other,
              f"{_other} / {fdlg.preview.font().family()}")
        fdlg._select("Microsoft YaHei UI")
        app.processEvents()
    check("字体对话框-列表用自身字体渲染",
          fdlg.font_list.count() > 0 and fdlg.font_list.currentItem() is not None
          and fdlg.font_list.currentItem().data(Qt.ItemDataRole.FontRole) is not None,
          f"count={fdlg.font_list.count()}")
    # 搜索过滤：当前项被滤掉时选择要落到第一条可见项上，预览不能停在看不见的字体
    fdlg.search.setText("yahei")
    app.processEvents()
    _cur = fdlg.font_list.currentItem()
    check("字体对话框-搜索过滤落到可见项",
          _cur is not None and not _cur.isHidden() and "yahei" in _cur.text().lower(),
          str(_cur.text() if _cur else "无"))
    fdlg.search.clear()
    app.processEvents()
    fdlg._restore_default()
    app.processEvents()
    family, size, weight, italic, line = fdlg.selected()
    check("字体对话框-恢复默认值回到 Settings 默认",
          family == _def_family and size == _def_size
          and weight == _settings_mod.Settings.font_weight
          and italic == _settings_mod.Settings.font_italic
          and line == _settings_mod.Settings.line_height_percent,
          f"{family}/{size}/{weight}/{italic}/{line}")
    check("字体对话框-预览跟随默认值", _pt(fdlg.preview) == _def_size,
          str(_pt(fdlg.preview)))
    # 字重/斜体/行距要真的影响预览（回归点：参数加了但预览不动 = 假选项）
    fdlg.weight_box.setCurrentIndex(2)          # 加粗
    fdlg.italic_box.setChecked(True)
    app.processEvents()
    check("字体对话框-预览跟随字重与斜体",
          fdlg.preview.font().weight() == 700 and fdlg.preview.font().italic(),
          f"{fdlg.preview.font().weight()}/{fdlg.preview.font().italic()}")
    fdlg.weight_box.setCurrentIndex(0)
    fdlg.italic_box.setChecked(False)
    app.processEvents()
    # 字号框的微调箭头（回归点：QSS 定制 up/down 按钮后 Qt 不画默认箭头；
    # 箭头规则在全局主题里 —— 主窗口样式表只剩编辑器专属段）
    check("SpinBox-微调箭头样式已定义",
          all(s in QApplication.instance().styleSheet()
              for s in ("up-arrow", "spin_up.png", "spin_down.png")))
    # 编辑器 QSS 带字重/斜体（QSS 优先于 setFont，缺了这两行参数就不生效）
    from app.ui.theme import editor_font_qss as _efq
    check("editor_font_qss-字重斜体生效",
          "font-weight: 700" in _efq("A", 12, 160, 700, True)
          and "font-style: italic" in _efq("A", 12, 160, 400, True)
          and "font-weight: 400" in _efq("A", 12, 160),
          _efq("A", 12, 160, 700, True))
    fdlg.close()

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
