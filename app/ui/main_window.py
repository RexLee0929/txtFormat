"""主窗口：菜单、命令栏、文件列表、编辑区、串替换面板、状态栏。"""

from __future__ import annotations

import copy
import os
import re
from datetime import datetime

from PySide6.QtCore import QEvent, QPoint, QSize, Qt
from PySide6.QtGui import QAction, QCursor, QFont, QGuiApplication, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QMainWindow, QMenu, QPlainTextEdit,
                               QSplitter, QStatusBar, QVBoxLayout, QWidget)

from ..core import adfilter, automation as automation_mod, convert as convert_mod
from ..core import encoding as enc
from ..core import formatter, punct, regexlib, splitter, zhconv
from ..core.settings import Settings
from ..core.version import APP_NAME, APP_VERSION, AUTHOR_EMAIL
from . import dialogs, icons
from .automation import AutomationPanel
from .editor import TextEditor
from .panels import FilePanel, ReplacePanel, human_size
from .theme import Color, editor_font_qss, stylesheet
from .task import start_task, task_running, wait_task
from .widgets import (Card, Caption, CommandButton, CompactComboBox,
                      ConfirmBar, IconButton, Menu, Toast)

ZERO_WIDTH = "\u200b"

# 字体对话框「恢复默认值」的出厂默认（简体中文 · 黑体 · 14 号）
DEFAULT_FONT_FAMILY = "黑体"
DEFAULT_FONT_SIZE = 14


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 首次运行就落盘一份默认 config.json（规范 §三.2：让"已有配置"成为常态，
        # 安装器才检测得到；已有则不动，旧 %APPDATA% 设置会先迁过来）。
        Settings.ensure_default()
        self.settings = Settings.load()
        self.lib = regexlib.RegexLibrary()
        self.path: str | None = None
        self.encoding = self.settings.save_encoding
        self.newline = self.settings.newline
        self.modified = False
        self._matches: list[tuple[int, int]] = []
        self._match_index = -1
        #: (缓存键, 匹配区间, 不同类型数) —— 见 _scan_matches()
        self._match_cache: tuple[tuple, list[tuple[int, int]], int] | None = None
        self._suppress_modified = False
        self._original_text = ""          # 打开文件时的原文，用于“还原”
        self._disk_text = ""              # 磁盘上当前的内容（保存后更新）
        self._save_confirmed = False      # 本次打开后是否已确认过覆盖保存
        self._pending_action = None       # 内联确认条上「确认」按下后要执行的回调
        self._closing = False             # 关窗确认通过后置位，避免再次触发

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(QSize(1160, 720))
        self.resize(1420, 880)
        self.command_buttons: list[CommandButton] = []
        self.setStyleSheet(stylesheet() + editor_font_qss(
            self.settings.font_family, self.settings.font_size, self.settings.line_height_percent))

        self._build_ui()
        self._build_menus()
        self._build_shortcuts()
        self._refresh_library()
        self._update_title()
        self._update_status()

    # ================================================================ 构建
    def resizeEvent(self, event):        # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        # 命令栏的「收起文字」由 CommandButton 自己在 resizeEvent 里按实际宽度决定，
        # 这里不用再排队算密度（旧实现要在下一拍手工重算，放大时还会漏恢复）。
        # 浮动提示贴着底边，窗口一变矮就得重新摆位。
        if hasattr(self, "toast") and self.toast.isVisible():
            self.toast._place()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        layout.addWidget(self._build_command_bar())

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)

        # ---- 左：文件列表
        left_card = Card(padding=12, spacing=8)
        self.file_panel = FilePanel()
        self.file_panel.file_activated.connect(self.open_path)
        self.file_panel.files_changed.connect(self._update_status)
        # 文件面板的失败（改名/删除）走状态栏红字提示，不静默吞掉
        self.file_panel.notify.connect(
            lambda msg: self.toast.show_message(msg, kind="error"))
        left_card.body().addWidget(self.file_panel)
        left_card.setMinimumWidth(330)
        left_card.setMaximumWidth(460)

        # ---- 中：编辑区
        center_card = Card(padding=10, spacing=6)
        header = QHBoxLayout()
        header.setSpacing(8)
        self.doc_title = QLabel("未命名")
        font = self.doc_title.font()
        font.setPointSizeF(10.5)
        font.setWeight(QFont.Weight.DemiBold)
        self.doc_title.setFont(font)
        header.addWidget(self.doc_title)
        self.doc_meta = Caption("")
        header.addWidget(self.doc_meta)
        header.addStretch(1)
        self.mode_btn = CommandButton("整理模式", "format")
        self.mode_btn.setProperty("compact", True)
        self.mode_btn.setCheckable(True)
        self.mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_btn.setToolTip("点击切换：整理模式 ⇄ 阅读模式")
        self.mode_btn.clicked.connect(self.apply_reading_mode)
        header.addWidget(self.mode_btn)
        center_card.body().addLayout(header)

        self.editor = TextEditor()
        self.editor.set_editor_font(self.settings.font_family, self.settings.font_size,
                                    self.settings.line_height_percent)
        self.editor.font_changed.connect(self._apply_editor_font_qss)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.stats_changed.connect(self._update_status)
        self.editor.set_guide_column(0)
        center_card.body().addWidget(self.editor, 1)

        # ---- 右：自动化 + 替换规则
        right_card = Card(padding=12, spacing=8)
        self.automation_panel = AutomationPanel(self.settings)
        self.automation_panel.run_requested.connect(self.run_automation)
        right_card.body().addWidget(self.automation_panel)
        self.replace_panel = ReplacePanel()
        self._wire_replace_panel()
        right_card.body().addWidget(self.replace_panel)
        right_card.setMinimumWidth(300)
        right_card.setMaximumWidth(420)

        self.splitter.addWidget(left_card)
        self.splitter.addWidget(center_card)
        self.splitter.addWidget(right_card)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([400, 700, 320])
        layout.addWidget(self.splitter, 1)

        # ---- 内联确认条（规范 §七 ③）
        # 不可逆操作（覆盖保存、还原、丢弃修改）不再弹模态框，
        # 而是在内容区底部浮出这一条，写清后果，主按钮直接写动词短语。
        self.confirm_bar = ConfirmBar(central)
        self.confirm_bar.confirmed.connect(self._on_confirm_bar_ok)
        self.confirm_bar.rejected.connect(self._on_confirm_bar_cancel)
        layout.addWidget(self.confirm_bar)

        # ---- 状态栏
        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.setStatusBar(status)
        self.pos_label = QLabel("行 1:列 1")
        self.sel_label = QLabel("选定 0 字符")
        self.count_label = QLabel("共 0 字")
        self.enc_label = QLabel("")
        self.mod_label = QLabel("")
        for w in (self.pos_label, self.sel_label, self.count_label):
            status.addWidget(self._status_sep())
            status.addWidget(w)
        status.addPermanentWidget(self.enc_label)
        status.addPermanentWidget(self._status_sep())
        status.addPermanentWidget(self.mod_label)

        self.toast = Toast(central)

    def _status_sep(self) -> QFrame:
        line = QFrame()
        line.setFixedSize(1, 12)
        line.setStyleSheet(f"background: {Color.border_strong}; margin: 0 8px;")
        return line

    def _build_command_bar(self) -> QWidget:
        bar = Card(padding=8, spacing=6)
        bar.body().setDirection(QVBoxLayout.Direction.TopToBottom)
        row = QHBoxLayout()
        row.setSpacing(4)

        def add(text: str, icon_name: str, slot, tip: str = "",
                primary: bool = False) -> CommandButton:
            """primary=True 的按钮在窗口变窄时也不收文字（主力功能，优先级最高）。"""
            btn = CommandButton(text, icon_name, collapse_when_tight=not primary)
            btn.clicked.connect(slot)
            if tip:
                btn.setToolTip(tip)
            row.addWidget(btn)
            self.command_buttons.append(btn)
            return btn

        add("打开", "open", self.open_file, "打开文本文件（Ctrl+O）", primary=True)
        add("保存", "save", self.save_file, "保存当前文档（Ctrl+S）", primary=True)
        self.btn_revert = add("还原", "undo", self.revert_to_original,
                              "放弃本次打开后的修改，还原为打开时的内容")
        self.btn_format = add("格式整理", "format", self.run_format,
                               "按选项设置整理全文或选定内容（Ctrl+D）", primary=True)
        add("一键审核", "check", self.run_audit,
            "快速检查错别字、标点、引号等问题（Ctrl+Shift+F）")
        add("广告检查", "clean", self.run_ad_check,
            "扫描广告，生成 remove.txt（Ctrl+Shift+A）")
        add("自定义替换", "replace", self.run_custom_replace,
            "按 remove.txt 删除已确认的广告")

        divider = QFrame()
        divider.setFixedWidth(1)
        divider.setStyleSheet(f"background: {Color.border}; margin: 4px 6px;")
        row.addWidget(divider)

        add("章节整理", "split", self.run_split_dialog, "文件分割 / 章节整理")
        add("合并", "merge", self.run_merge_dialog, "文件更名 / 文件合并")
        self.btn_zhconv = add("简繁", "convert", self.run_zhconv, "简体 ↔ 繁体转换")
        add("转到", "goto", self.run_goto, "跳转到指定行或百分比（Ctrl+G）")

        divider2 = QFrame()
        divider2.setFixedWidth(1)
        divider2.setStyleSheet(f"background: {Color.border}; margin: 4px 6px;")
        row.addWidget(divider2)

        self.convert_combo = CompactComboBox(rows=8)
        self.convert_combo.setMinimumHeight(32)
        self.convert_combo.setMinimumWidth(132)
        for name, (exts, desc, _) in convert_mod.CONVERTERS.items():
            self.convert_combo.addItem(desc, name)
        row.addWidget(self.convert_combo)
        add("转换", "convert", self.run_convert, "把当前文件转换为纯文本", primary=True)

        row.addStretch(1)

        self.search_box = IconButton("search", "在文件中查找（Ctrl+F）", size=32)
        self.search_box.clicked.connect(self.focus_find)
        row.addWidget(self.search_box)
        settings_btn = IconButton("settings", "选项设置", size=32)
        settings_btn.clicked.connect(self.open_settings)
        row.addWidget(settings_btn)

        # 非按钮的固定宽度控件：算总宽时要一起算进去
        self._bar_fixed = [divider, divider2, self.convert_combo,
                           self.search_box, settings_btn]
        self._bar_spacing = row.spacing()

        bar.body().addLayout(row)
        self._bar_widget = bar
        # 命令栏自己的 resize 事件即可拿到**新**宽度（不必像旧实现那样排到下一拍：
        # 那时读到的还是上一帧的旧宽度，缩小时漏收、放大时不恢复）。
        bar.installEventFilter(self)
        return bar

    # ---------------------------------------------------------------- 命令栏自适应
    def eventFilter(self, obj, event):       # noqa: N802 - Qt 命名
        if obj is self._bar_widget and event.type() == QEvent.Type.Resize:
            self._fit_command_bar()
        return super().eventFilter(obj, event)

    def _fit_command_bar(self) -> None:
        """按命令栏可用宽度决定哪些按钮收起文字。

        QBoxLayout 只会把放不下的项**按比例压扁**（文字被裁成「一键审」），没有
        "按重要性依次收起"的原生机制，所以这一步只能自己算 —— 但做得很小：
        按钮自报两种宽度，命令栏先按全文字排一遍，再从不重要的开始收，直到装下。
        **每次 resize 都从"全部展开"重算**，不保存收起集合，因此不存在
        「缩小再放大文字不回来」的中间态。
        """
        if not self.command_buttons or self._bar_widget is None:
            return
        margins = self._bar_widget.body().contentsMargins()
        avail = self._bar_widget.width() - margins.left() - margins.right()
        if avail <= 0:
            return

        # 1) 先按「完整文字」排一遍
        for btn in self.command_buttons:
            btn.set_label_visible(True)
            btn.setFixedWidth(btn.natural_width())

        fixed = sum(w.sizeHint().width() for w in self._bar_fixed)
        spacing = self._bar_spacing * (len(self.command_buttons) + len(self._bar_fixed))

        def wanted() -> int:
            """按「当前该显示的文字」算出的总宽（不信 width()，它还是旧值）。"""
            return (sum(b.natural_width() if b.text() else b.compact_width()
                        for b in self.command_buttons) + fixed + spacing)

        if wanted() <= avail:
            return

        # 2) 从不重要的开始收：从右到左（越靠右越次要），主力按钮不参与
        for btn in reversed(self.command_buttons):
            if not btn.collapse_when_tight:
                continue
            btn.set_label_visible(False)
            btn.setFixedWidth(btn.compact_width())
            if wanted() <= avail:
                break

    def visible_command_labels(self) -> list[str]:
        """当前还在显示文字的命令按钮（自检/测试用）。"""
        return [b.text() for b in self.command_buttons if b.text()]

    # ---------------------------------------------------------------- 菜单
    def _build_menus(self) -> None:
        menubar = self.menuBar()

        # 弹层全部用自绘 Menu（规范 §五：白色圆角卡片、快捷键灰、分隔线缩进）
        m_file = self._add_menu(menubar, "文件(&F)")
        self._action(m_file, "新建", "Ctrl+N", self.new_file, "new")
        self._action(m_file, "打开…", "Ctrl+O", self.open_file, "open")
        self._action(m_file, "保存", "Ctrl+S", self.save_file, "save")
        self._action(m_file, "另存为…", "Ctrl+Shift+S", self.save_file_as, "save-as")
        m_file.addSeparator()
        self._action(m_file, "打开所在文件夹", "", self.reveal_in_explorer, "folder")
        m_file.addSeparator()
        self.act_revert = self._action(m_file, "还原为打开时的内容", "", self.revert_to_original, "undo")
        self.act_revert.setEnabled(False)
        m_file.addSeparator()
        self._action(m_file, "退出", "Esc", self.close, "close")

        m_edit = self._add_menu(menubar, "编辑(&E)")
        self._action(m_edit, "撤消", "Ctrl+Z", self.editor_undo, "undo")
        self._action(m_edit, "恢复", "Ctrl+Shift+Z", self.editor_redo, "redo")
        m_edit.addSeparator()
        self._action(m_edit, "剪切", "Ctrl+X", lambda: self.editor.cut(), "outdent")
        self._action(m_edit, "复制", "Ctrl+C", lambda: self.editor.copy(), "copy")
        self._action(m_edit, "粘贴", "Ctrl+V", lambda: self.editor.paste(), "insert")
        self._action(m_edit, "全选", "Ctrl+A", lambda: self.editor.selectAll(), "check")
        m_edit.addSeparator()
        self._action(m_edit, "转到…", "Ctrl+G", self.run_goto, "goto")
        self._action(m_edit, "向下查找下一个", "F3", lambda: self.find_next(True), "next")
        self._action(m_edit, "向上查找上一个", "Shift+F3", lambda: self.find_next(False), "prev")
        m_edit.addSeparator()
        m_ins = self._add_menu(m_edit, "插入")
        self._action(m_ins, "插入符号：“", "", lambda: self.insert_text("“"), "insert")
        self._action(m_ins, "插入符号：……", "", lambda: self.insert_text("……"), "insert")
        self._action(m_ins, "插入分隔线：※※※", "", lambda: self.insert_text("※※※"), "insert")
        self._action(m_ins, "插入日期", "Ctrl+Shift+D", self.insert_date, "file")
        self._action(m_ins, "插入文件名", "", self.insert_filename, "file")

        m_sel = self._add_menu(m_edit, "选定内容")
        self._action(m_sel, "制表符缩进", "Tab", lambda: self.indent_selection("tab", 1), "indent")
        self._action(m_sel, "制表符反缩进", "Shift+Tab", lambda: self.indent_selection("tab", -1), "outdent")
        self._action(m_sel, "空格缩进", "", lambda: self.indent_selection(self.settings.indent_kind, 1), "indent")
        self._action(m_sel, "空格反缩进", "", lambda: self.indent_selection(self.settings.indent_kind, -1), "outdent")
        self._action(m_sel, "去除行尾空格", "", self.strip_tail_spaces, "clean")
        m_sel.addSeparator()
        self._action(m_sel, "转为大写", "", lambda: self.change_case("upper"), "case")
        self._action(m_sel, "转为小写", "", lambda: self.change_case("lower"), "case")
        self._action(m_sel, "首尾引号规范化", "", self.normalize_quotes, "format")

        m_view = self._add_menu(menubar, "查看(&V)")
        self._action(m_view, "字体…", "", self.choose_font, "font")
        self.act_wrap = self._action(m_view, "自动换行", "Ctrl+U", self.toggle_wrap, "wrap", checkable=True)
        self.act_wrap.setChecked(self.settings.word_wrap)
        self.act_status = self._action(m_view, "状态栏", "", self.toggle_statusbar, "list", checkable=True)
        self.act_status.setChecked(True)
        self.act_onscreen = self._action(m_view, "总在最前", "Ctrl+T", self.toggle_always_on_top, "pin", checkable=True)
        m_view.addSeparator()
        self.act_reading = self._action(m_view, "阅读模式", "", self.toggle_reading_mode, "read", checkable=True)
        self.act_scroll = self._action(m_view, "自动卷屏", "", self.toggle_auto_scroll, "scroll", checkable=True)
        self.act_guide = self._action(m_view, "显示水线", "", self.toggle_guide, "rulers", checkable=True)
        m_view.addSeparator()
        self._action(m_view, "统计选定（全部）内容", "", self.show_stats, "stats")

        m_tools = self._add_menu(menubar, "工具(&T)")
        self._action(m_tools, "格式整理", "Ctrl+D", self.run_format, "format")
        self._action(m_tools, "格式整理选项…", "", self.open_settings, "settings")
        m_tools.addSeparator()
        self._action(m_tools, "广告检查及字符串计数", "Ctrl+Shift+A", self.run_ad_check, "clean")
        self._action(m_tools, "自定义替换/删除", "", self.run_custom_replace, "replace")
        m_tools.addSeparator()
        self._action(m_tools, "查找乱码", "", self.find_garbled, "search")
        self._action(m_tools, "修复选定乱码", "", self.fix_garbled, "search")
        m_tools.addSeparator()
        self._action(m_tools, "文件分割 / 章节整理…", "", self.run_split_dialog, "split")
        self._action(m_tools, "文件更名 / 文件合并…", "", self.run_merge_dialog, "merge")
        self._action(m_tools, "重编码…", "", self.run_recode, "convert")
        m_tools.addSeparator()
        self._action(m_tools, "以 ANSI 方式重新打开", "", lambda: self.reopen_with("gb18030"), "reopen")
        self._action(m_tools, "以 UTF-8 方式重新打开", "", lambda: self.reopen_with("utf-8"), "reopen")
        self._action(m_tools, "以 Unicode 方式重新打开", "", lambda: self.reopen_with("utf-16-le"), "reopen")
        m_tools.addSeparator()
        self._action(m_tools, "重新载入自定义正则", "", self._reload_regex, "refresh")

        # 规范 §八：帮助菜单**只放两项** ——「关于」+ 作者邮箱（直接显示邮箱本身，点了复制）。
        # 「重新载入自定义正则」是维护动作，挪到「工具」里，不占帮助的位置。
        m_help = self._add_menu(menubar, "帮助(&H)")
        self._action(m_help, "关于 " + APP_NAME, "", self.show_about, "info")
        self._action(m_help, AUTHOR_EMAIL, "", self.copy_contact, "mail")

    @staticmethod
    def _add_menu(parent, title: str) -> Menu:
        """往菜单栏/上级菜单里挂一个自绘弹层 Menu（规范 §五 的白色卡片外观）。"""
        menu = Menu(parent)
        menu.setTitle(title)
        parent.addMenu(menu)
        return menu

    def _action(self, menu: QMenu, text: str, shortcut: str, slot, icon_name: str = "",
                checkable: bool = False) -> QAction:
        action = QAction(text, self)
        if icon_name:
            action.setIcon(icons.icon(icon_name, Color.text, 16))
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        if checkable:
            # 规范 §五：可勾选项选中时，在图标列位置显示强调色勾（不显示该项图标）
            self._sync_check_icon(action, icon_name)
            action.toggled.connect(lambda _checked, a=action, n=icon_name:
                                   self._sync_check_icon(a, n))
            action.toggled.connect(slot)
        else:
            action.triggered.connect(slot)
        menu.addAction(action)
        return action

    @staticmethod
    def _sync_check_icon(action: QAction, icon_name: str) -> None:
        if not icon_name:
            return
        if action.isChecked():
            action.setIcon(icons.accent_icon("check", 16))
        else:
            action.setIcon(icons.icon(icon_name, Color.text, 16))

    def _build_shortcuts(self) -> None:
        # 只在这里注册**菜单里没有**的快捷键。F3 / Shift+F3 / Ctrl+G / Ctrl+D
        # 已经挂在菜单项（QAction）上，再建 QShortcut 会让同一个键绑两处：
        # Qt 判成 AmbiguousShortcut 时一次都不触发，否则会触发两遍
        # （实测 F3 连跳两条、Ctrl+D 整理两次）。
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.focus_find)
        QShortcut(QKeySequence("Ctrl+Shift+F"), self, activated=self.run_audit)
        QShortcut(QKeySequence("Ctrl+="), self, activated=lambda: self.zoom(1))
        QShortcut(QKeySequence("Ctrl+-"), self, activated=lambda: self.zoom(-1))

    # ================================================================ 文档
    def _update_title(self) -> None:
        name = os.path.basename(self.path) if self.path else "未命名"
        star = " *" if self.modified else ""
        self.setWindowTitle(f"{name}{star} — {APP_NAME} {APP_VERSION}")
        self.doc_title.setText(name)
        if self.path:
            try:
                size = human_size(os.path.getsize(self.path))
            except OSError:
                size = "-"
            self.doc_meta.setText(f"{size} · {enc.ENCODING_LABELS.get(self.encoding, self.encoding.upper())}")
        else:
            self.doc_meta.setText("尚未保存")
        self.mod_label.setText("已修改" if self.modified else "未修改")
        self.mod_label.setStyleSheet(
            f"color: {Color.warning if self.modified else Color.text_tertiary}; padding: 0 4px;")
        if hasattr(self, "act_revert"):
            self.act_revert.setEnabled(self.editor.toPlainText() != self._original_text)
        if hasattr(self, "btn_revert"):
            self.btn_revert.setEnabled(self.editor.toPlainText() != self._original_text)

    def _on_text_changed(self) -> None:
        if self._suppress_modified:
            return
        if not self.modified:
            self.modified = True
            self._update_title()
        self._update_status()

    def _update_status(self) -> None:
        cursor = self.editor.textCursor()
        block = cursor.blockNumber() + 1
        col = cursor.positionInBlock() + 1
        self.pos_label.setText(f"行 {block}:列 {col}")
        # 不要用 toPlainText() 统计：每次按键都会把整篇文档复制一份字符串，
        # 长篇小说（几 MB）下打字就卡。QTextDocument.characterCount() 是
        # 现成的字数（含末尾段落分隔符，减 1 即真实字符数），零拷贝。
        count = max(0, self.editor.document().characterCount() - 1)
        self.count_label.setText(f"共 {count} 字")
        self.sel_label.setText(f"选定 {cursor.selectionEnd() - cursor.selectionStart()} 字符")
        self.enc_label.setText(enc.ENCODING_LABELS.get(self.encoding, self.encoding.upper()))

    def _set_text(self, text: str, path: str | None = None) -> None:
        self._suppress_modified = True
        self.editor.setPlainText(text)
        self._suppress_modified = False
        self.modified = False
        self.path = path
        self._original_text = text
        self._disk_text = text
        self._save_confirmed = False
        self._matches = []
        self.editor.clear_highlights()
        self._update_title()
        self._update_status()
        self.editor.setFocus()

    # ---------------------------------------------------------------- 文件
    def _replace_document_text(self, new_text: str) -> None:
        """整篇替换正文，**保留撤销栈与光标位置**。

        全项目一律走这里，不要再 ``setPlainText()``：setPlainText 会清空撤销栈、
        把光标扔回文首、重建文档 —— 用户整理完一按 Ctrl+Z 发现撤不回去，
        光标也跳走，看起来就像「改了但没改对」。QTextCursor 的单次编辑块
        既保留撤销（一次 Ctrl+Z 回到替换前），也不动滚动位置。
        """
        cursor = self.editor.textCursor()
        position = cursor.position()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.insertText(new_text)
        cursor.endEditBlock()
        cursor.setPosition(min(position, len(new_text)))
        self.editor.setTextCursor(cursor)
        self.modified = True
        self._update_title()

    def new_file(self) -> None:
        if not self._confirm_discard():
            return
        self._set_text("", None)
        self.encoding = self.settings.save_encoding
        self.newline = self.settings.newline
        self.toast.show_message("已新建空白文档")

    def open_file(self) -> None:
        if not self._confirm_discard():
            return
        start = self.settings.last_dir or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要打开的文件", start,
            "文本文件 (*.txt *.log *.ini *.htm *.html);;所有文件 (*.*)")
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        if not self._confirm_discard():
            return
        try:
            doc = enc.read_text(path)
        except OSError as exc:
            # 规范 §七 ①：失败用状态栏瞬时提示（红字），不弹系统框、不发声
            self.toast.show_message(f"打开失败：{exc}", kind="error")
            return
        self.encoding = doc.encoding
        self.newline = doc.newline
        self._set_text(doc.text, path)
        self.settings.last_dir = os.path.dirname(path)
        self.file_panel.add_files([path])
        self.toast.show_message(f"已打开 {os.path.basename(path)}（{doc.label}）")

    def save_file(self) -> None:
        if not self.path:
            self.save_file_as()
            return
        if not self._confirm_save():
            return
        self._write(self.path)

    def _confirm_save(self) -> bool:
        """覆盖保存前询问一次（同一份文档本次只问一次，避免重复打扰）。

        规范 §七 ③：不可逆操作做内联确认条，不弹模态框。
        """
        if self._save_confirmed or not os.path.exists(self.path or ""):
            return True
        self._ask_confirm(
            f"要把当前修改覆盖保存到原文件吗？\n{self.path}\n\n"
            "原文件将被覆盖；如需保留原样，请用「另存为」。",
            "覆盖保存",
            self._do_overwrite_save,
            danger=True,
        )
        return False

    def _do_overwrite_save(self) -> None:
        self._save_confirmed = True
        self._write(self.path)

    def save_file_as(self) -> None:
        start = self.path or os.path.join(self.settings.last_dir or os.path.expanduser("~"), "未命名.txt")
        path, _ = QFileDialog.getSaveFileName(self, "另存为", start, "文本文件 (*.txt);;所有文件 (*.*)")
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".txt"
        self.path = path
        self._write(path)

    def _write(self, path: str) -> None:
        text = self.editor.toPlainText()
        try:
            enc.save_text(path, text, self.encoding, self.newline)
        except OSError as exc:
            # 规范 §七 ①：失败用状态栏瞬时提示（红字），不弹系统框
            self.toast.show_message(f"保存失败：{exc}", kind="error")
            return
        self.modified = False
        self._disk_text = text
        self._save_confirmed = True
        self.settings.last_dir = os.path.dirname(path)
        self._update_title()
        self.toast.show_message(f"已保存 {os.path.basename(path)}")

    def reveal_in_explorer(self) -> None:
        if not self.path:
            return
        try:
            os.startfile(os.path.dirname(self.path))       # noqa: S606
        except OSError:
            pass

    def reopen_with(self, codec: str) -> None:
        if not self.path or not self._confirm_discard():
            return
        doc = enc.read_text(self.path, codec)
        self.encoding = doc.encoding
        self._set_text(doc.text, self.path)
        self.toast.show_message(f"已以 {doc.label} 方式重新打开")

    def revert_to_original(self) -> None:
        """放弃本次打开后的修改，回到刚打开时的内容（保存过也能还原）。"""
        if self.editor.toPlainText() == self._original_text:
            self.toast.show_message("当前内容与打开时一致")
            return
        # 规范 §七 ③：不可逆操作做内联确认条
        self._ask_confirm("放弃本次打开后的所有修改，恢复到刚打开时的内容吗？",
                          "放弃并还原", self._do_revert, danger=True)

    def _do_revert(self) -> None:
        self._suppress_modified = True
        self.editor.setPlainText(self._original_text)
        self._suppress_modified = False
        self.modified = self._original_text != self._disk_text
        self._matches = []
        self.editor.clear_highlights()
        self._update_title()
        self._update_status()
        self.toast.show_message("已还原为打开时的内容")

    # ================================================================ 内联确认
    # 规范 §七 ③：不可逆操作做**内联确认**（内容区底部浮出确认条），
    # 不用模态框 —— 弹窗会把流程打断，用户连文档状态都看不见。
    def _ask_confirm(self, text: str, ok_text: str, action, danger: bool = False) -> None:
        """弹出内联确认条。

        ``action`` 是用户点「确认」后要执行的回调。
        ``danger`` 切换主按钮的危险态（红底）—— 必须走 set_danger 的
        repolish 路径，直接 setProperty 不会重新应用 QSS（实测踩过）。
        """
        self._pending_action = action
        self.confirm_bar.set_danger(danger)
        self.confirm_bar.show_for(text, ok_text)

    def _on_confirm_bar_ok(self) -> None:
        action = self._pending_action
        self._pending_action = None
        self.confirm_bar.hide()
        if action is not None:
            action()

    def _on_confirm_bar_cancel(self) -> None:
        self._pending_action = None
        self.confirm_bar.hide()

    def _confirm_discard(self, after: str = "") -> bool:
        """文档有改动时需要确认。

        返回 True = 可以继续；False = 已弹出确认条、当前操作中止，
        用户点确认后由 ``_pending_action`` 接着做。
        """
        if not self.modified:
            return True

        def do_discard() -> None:
            self.modified = False
            self._disk_text = self.editor.toPlainText()
            self._update_title()
            self._update_status()
            self.toast.show_message("已放弃修改")
            if after:
                getattr(self, after)()

        self._ask_confirm(
            "文档内容已更改。要保存修改后再继续吗？",
            "放弃修改并继续",
            do_discard,
        )
        return False

    def closeEvent(self, event):                      # noqa: N802
        # 后台任务还在跑就等它收尾：QThread 在运行中被析构会让进程直接崩
        # （QThread: Destroyed while thread is still running）。等不到就干脆不让关，
        # 免得把几秒的计算连窗口一起丢掉。
        if task_running(self):
            wait_task(self, 3000)
            if task_running(self):
                self.toast.show_message("正在处理中，请稍候再退出", kind="error")
                event.ignore()
                return
        if self._closing:
            # 已经过确认（用户点了「放弃并退出」），这次是真正的关闭
            self.settings.save()
            event.accept()
            return
        if self.modified:
            # 关窗也要确认 —— 同样走内联确认条，条上点「放弃并退出」
            def do_close() -> None:
                self._closing = True
                self.close()

            self._ask_confirm("文档内容已更改，退出将丢失未保存的修改。",
                              "放弃并退出", do_close, danger=True)
            event.ignore()
            return
        self.settings.save()
        event.accept()

    # ================================================================ 查找替换
    def _wire_replace_panel(self) -> None:
        p = self.replace_panel
        p.populate(self.lib.entries)
        p.library_selected.connect(self._on_library_selected)
        p.find_requested.connect(lambda _text: self.find_next(True))
        p.find_prev_requested.connect(lambda: self.find_next(False))
        p.replace_one_requested.connect(self.replace_current)
        p.replace_all_requested.connect(self.replace_all)
        # 多行输入框里回车是换行，Ctrl+回车 直接触发查找
        p.find_edit.submitted.connect(lambda: self.find_next(True))

    def _refresh_library(self) -> None:
        self.replace_panel.populate(self.lib.entries)

    def _reload_regex(self) -> None:
        self.lib.reload()
        self._refresh_library()
        self.toast.show_message(f"已重新载入 {len(self.lib.entries)} 条正则表达式")

    def _on_library_selected(self, index: int) -> None:
        if index <= 0:
            return
        entry = self.lib.entries[index - 1]
        if entry.is_checker:
            self.replace_panel.note.setText(entry.note or "这是一个检查器，请使用“一键审核”。")
            self.run_audit(preselect=entry.checker)
            return
        self.replace_panel.apply_entry(entry)
        self.find_next(True)

    def _pattern(self) -> tuple[str, bool, bool]:
        """返回 (表达式, 是否正则, 是否忽略大小写)。"""
        panel = self.replace_panel
        text = panel.find_edit.text()
        if not text:
            index = panel.current_library_index()
            if index > 0:
                entry = self.lib.entries[index - 1]
                text = entry.pattern
        if not panel.use_regex:
            text = re.escape(text)
        return text, panel.use_regex, panel.ignore_case

    def focus_find(self) -> None:
        self.replace_panel.find_edit.setFocus()
        self.replace_panel.find_edit.selectAll()

    def _scan_matches(self, pattern: str, ignore_case: bool) -> tuple[list[tuple[int, int]], int]:
        """扫出全部匹配区间，并按「文档修订号」缓存。

        旧实现每按一次 F3 都 ``toPlainText()`` 复制整篇文档 + ``finditer`` 全量重扫，
        再对每处匹配切片做一次 ``set`` 统计「几种类型」—— 5MB 小说每次 F3 都是
        几百毫秒的同步卡顿。文档没改（``revision()`` 不变、正则没变）时直接用上次
        的结果；一旦编辑过，修订号变了，缓存自然失效。
        """
        revision = self.editor.document().revision()
        key = (pattern, bool(ignore_case), revision)
        if self._match_cache is not None and self._match_cache[0] == key:
            return self._match_cache[1], self._match_cache[2]
        rx = regexlib.compile_pattern(pattern, ignore_case)
        text = self.editor.toPlainText()
        spans = [(m.start(), m.end()) for m in rx.finditer(text)]
        kinds = len({text[s:e] for s, e in spans})
        self._match_cache = (key, spans, kinds)
        return spans, kinds

    def find_next(self, forward: bool = True) -> None:
        pattern, _is_regex, ignore_case = self._pattern()
        if not pattern:
            self.toast.show_message("请先选择一条正则表达式或输入要查找的内容")
            return
        cursor = self.editor.textCursor()
        try:
            spans, kinds = self._scan_matches(pattern, ignore_case)
        except re.error as exc:
            self.toast.show_message(f"正则表达式有误：{exc}")
            return
        total = len(spans)
        if not spans:
            self.editor.clear_highlights()
            self._matches = []
            self.toast.show_message("未找到匹配结果。")
            return
        self._matches = spans
        pos = cursor.selectionStart() if cursor.hasSelection() else cursor.position()
        if forward:
            index = next((i for i, (s, _e) in enumerate(spans) if s > pos - 1 and (s, _e) !=
                          (cursor.selectionStart(), cursor.selectionEnd())), None)
            if index is None:
                index = 0
        else:
            index = next((i for i in range(len(spans) - 1, -1, -1)
                          if spans[i][0] < pos), len(spans) - 1)
        self._match_index = index
        self._select_match(index)
        self.editor.highlight_matches(spans, index)
        self.toast.show_message(f"共找到 {kinds} 种不同类型 {total} 处")

    def _select_match(self, index: int) -> None:
        start, end = self._matches[index]
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.centerCursor()

    def replace_current(self) -> None:
        pattern, _is_regex, ignore_case = self._pattern()
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            self.find_next(True)
            return
        replacement = self.replace_panel.repl_edit.text()
        try:
            rx = regexlib.compile_pattern(pattern, ignore_case)
            match = rx.fullmatch(cursor.selectedText())
            new_text = match.expand(regexlib.convert_replacement(replacement)) if match else replacement
        except re.error:
            new_text = replacement
        cursor.insertText(new_text)
        self.find_next(True)

    def replace_all(self, selection_only: bool = False) -> None:
        pattern, _is_regex, ignore_case = self._pattern()
        if not pattern:
            self.toast.show_message("请先选择一条正则表达式或输入要查找的内容")
            return
        replacement = self.replace_panel.repl_edit.text()
        cursor = self.editor.textCursor()
        if selection_only and cursor.hasSelection():
            start, end = cursor.selectionStart(), cursor.selectionEnd()
        else:
            start, end = 0, len(self.editor.toPlainText())

        if self.replace_panel.batch and self.file_panel.paths():
            self._batch_replace(pattern, replacement, ignore_case)
            return

        text = self.editor.toPlainText()
        try:
            new_text, count = regexlib.replace_all(text, pattern, replacement, ignore_case, start, end)
        except re.error as exc:
            self.toast.show_message(f"正则表达式有误：{exc}")
            return
        if count:
            self._replace_document_text(new_text)
        self.editor.highlight_matches([])
        self.toast.show_message(f"替换完成，共完成 {count} 处替换，注意及时保存处理结果。" if count else "没有找到匹配内容。")

    def _batch_replace(self, pattern: str, replacement: str, ignore_case: bool) -> None:
        files = self.file_panel.paths()
        # 规范 §七 ③：要写回磁盘的不可逆操作做内联确认条
        self._ask_confirm(
            f"将对列表中 {len(files)} 个文件执行替换，并直接写回磁盘（自动保留原编码）。",
            f"替换并写回 {len(files)} 个文件",
            lambda: self._do_batch_replace(pattern, replacement, ignore_case),
            danger=True,
        )

    def _do_batch_replace(self, pattern: str, replacement: str, ignore_case: bool) -> None:
        files = self.file_panel.paths()
        done = 0
        failed = 0
        for path in files:
            try:
                doc = enc.read_text(path)
                new_text, count = regexlib.replace_all(doc.text, pattern, replacement, ignore_case)
                if count:
                    enc.save_text(path, new_text, doc.encoding, doc.newline, keep_bom=doc.has_bom)
                    done += count
            except (OSError, re.error):
                failed += 1
        self.toast.show_message(f"批处理完成，共完成 {done} 处替换" + (f"，{failed} 个文件失败" if failed else ""))

    # ================================================================ 工具
    def run_format(self) -> None:
        cursor = self.editor.textCursor()
        has_selection = cursor.hasSelection()
        source = cursor.selectedText().replace("\u2029", "\n") if has_selection else self.editor.toPlainText()
        if not source.strip():
            self.toast.show_message("没有可整理的内容")
            return
        # 全文整理要跑一串正则，5MB 小说是秒级 —— 放到后台线程，别让窗口假死。
        # 设置也复制一份：后台线程读的是快照，用户中途改选项不会读出半新半旧的值。
        revision = self.editor.document().revision()
        span = (cursor.selectionStart(), cursor.selectionEnd())
        settings = copy.deepcopy(self.settings)

        def work():
            return formatter.format_text(source, settings)

        def apply(result) -> None:
            if self.editor.document().revision() != revision:
                self.toast.show_message("正文在整理过程中被改动，本次结果已丢弃")
                return
            if not result.changed:
                self.toast.show_message("整理完成，文档已经是规范格式")
                return
            if has_selection:
                edit = QTextCursor(self.editor.document())
                edit.setPosition(span[0])
                edit.setPosition(span[1], QTextCursor.MoveMode.KeepAnchor)
                edit.insertText(result.text)
                self.modified = True
                self._update_title()
            else:
                self._replace_document_text(result.text)
            stats = result.stats.as_text()
            scope = "选定内容" if has_selection else "全文"
            self.toast.show_message(f"整理完成（{scope}）：{stats}" if stats else "整理完成!")

        self._start_busy_task(work, apply, "正在整理…")

    def run_audit(self, preselect: str | None = None) -> None:
        dialog = dialogs.QuickReviewDialog(self.editor.toPlainText(), self)
        if preselect:
            dialog.preselect({preselect, "punct", "quotes", "brackets"})
        if dialog.exec() == QDialog.DialogCode.Accepted and hasattr(dialog, "selected_offset"):
            cursor = self.editor.textCursor()
            cursor.setPosition(min(dialog.selected_offset, len(self.editor.toPlainText())))
            self.editor.setTextCursor(cursor)
            self.editor.centerCursor()

    def run_ad_check(self) -> None:
        pattern, _is_regex, ignore_case = self._pattern()
        if not pattern:
            entry = self.lib.get("查找 广告及其它问题……")
            pattern = entry.pattern if entry else ""

        text = self.editor.toPlainText()
        base = os.path.dirname(self.path) if self.path else os.path.expanduser("~")

        def work():
            return (adfilter.scan(text, pattern, ignore_case),
                    regexlib.count_matches(text, pattern, ignore_case)[0])

        def apply(result) -> None:
            fragments, total = result
            if not fragments:
                self.toast.show_message("未找到匹配结果。")
                return
            remove_path = adfilter.default_remove_path(base)
            replace_path = adfilter.default_replace_path(base)
            try:
                adfilter.write_remove_list(remove_path, fragments)
                with open(replace_path, "w", encoding="utf-8", newline="\r\n") as fh:
                    fh.write("\n".join(f"{frag}\t" for frag in fragments))
            except OSError as exc:
                self.toast.show_message(f"写入失败：{exc}", kind="error")
                return
            # 规范 §七 ①：成功反馈走状态栏瞬时提示
            self.toast.show_message(
                f"共找到 {len(fragments)} 种对象 {total} 条，已写入 {os.path.basename(remove_path)}。")
            try:
                os.startfile(remove_path)                   # noqa: S606
            except OSError:
                pass

        def failed(message: str) -> None:
            self._end_busy_task()
            self.toast.show_message(f"正则表达式有误：{message}", kind="error")

        self._start_busy_task(work, apply, "正在扫描广告…")

    def run_custom_replace(self) -> None:
        base = os.path.dirname(self.path) if self.path else (self.settings.last_dir or os.path.expanduser("~"))
        remove_path = adfilter.default_remove_path(base)
        if not os.path.exists(remove_path):
            path, _ = QFileDialog.getOpenFileName(self, "选择要使用的 remove.txt", base, "文本文件 (*.txt)")
            if not path:
                return
            remove_path = path
        fragments = adfilter.read_remove_list(remove_path)
        if not fragments:
            self.toast.show_message("remove.txt 中没有内容。")
            return
        # 规范 §七 ③：删除内容不可逆，做内联确认条
        self._ask_confirm(
            f"将按 {os.path.basename(remove_path)} 中的 {len(fragments)} 条内容"
            "从当前文档中删除。",
            f"删除 {len(fragments)} 处",
            lambda: self._do_custom_replace(fragments),
            danger=True,
        )

    def run_automation(self, task: dict) -> None:
        """执行一个自动化任务：按步骤顺序批量处理当前文档。

        步骤配置全部存在任务里（core.automation 执行时只读步骤自带配置），
        程序自身的选项设置不受影响；整篇结果一次性替换，一次 Ctrl+Z 可整体撤销。
        """
        steps = task.get("steps") or []
        if not steps:
            self.toast.show_message("这个任务还没有添加任何功能，请先编辑。")
            return
        text = self.editor.toPlainText()
        if not text.strip():
            self.toast.show_message("没有可处理的内容")
            return
        base_dir = os.path.dirname(self.path) if self.path else \
            (self.settings.last_dir or os.path.expanduser("~"))
        revision = self.editor.document().revision()

        def work():
            return automation_mod.run_automation(text, steps, base_dir)

        def apply(result) -> None:
            new_text, notes = result
            if self.editor.document().revision() != revision:
                self.toast.show_message("正文在执行过程中被改动，本次结果已丢弃")
                return
            if new_text != text:
                self._replace_document_text(new_text)
            # 记录「上次调用的自动化」（只写这一个字段，不碰其它配置）
            self.settings.last_automation = task["name"]
            self.settings.save()
            self.toast.show_message(
                f"自动化「{task['name']}」完成：\n" + "\n".join(notes), msec=4200)

        self._start_busy_task(work, apply, "正在执行自动化…")

    def _start_busy_task(self, work, apply, busy_text: str) -> None:
        """在后台线程跑 ``work()``，完成后用 ``apply(result)`` 回到 UI 线程处理。

        跑的时候状态栏显示进度文字、光标变忙；同一时间只允许一个后台任务
        （两个任务都改正文时会互相覆盖）。
        """
        if task_running(self):
            self.toast.show_message("上一个处理还没完成，请稍候")
            return
        self.statusBar().showMessage(busy_text)
        self.setCursor(Qt.CursorShape.BusyCursor)

        def done(result) -> None:
            self._end_busy_task()
            apply(result)

        def failed(message: str) -> None:
            self._end_busy_task()
            self.toast.show_message(f"处理失败：{message}", kind="error")

        start_task(self, work, done, failed)

    def _end_busy_task(self) -> None:
        self.unsetCursor()
        self.statusBar().clearMessage()

    def _do_custom_replace(self, fragments: list[str]) -> None:
        text = self.editor.toPlainText()
        revision = self.editor.document().revision()

        def apply(result) -> None:
            new_text, count = result
            if count and self.editor.document().revision() != revision:
                self.toast.show_message("正文在删除过程中被改动，本次结果已丢弃")
                return
            if count:
                self._replace_document_text(new_text)
            self.toast.show_message(f"共删除 {count} 处内容!" if count else "没有找到可删除的内容。")

        self._start_busy_task(lambda: adfilter.apply_remove_list(text, fragments),
                              apply, "正在删除…")

    def run_split_dialog(self) -> None:
        dialog = dialogs.SplitDialog(self.editor.toPlainText(), self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.result_text != self.editor.toPlainText():
            self._replace_document_text(dialog.result_text)
        request = dialog.split_requested
        if not request:
            return
        text = dialog.result_text
        if request["by_chapter"]:
            result = splitter.split_by_chapter(text, request["pattern"], request["out_dir"],
                                               request["prefix"], self.encoding, self.newline)
        else:
            result = splitter.split_by_size(text, request["size_kb"], request["out_dir"],
                                            request["prefix"], self.encoding, self.newline)
        self.toast.show_message(f"已生成 {len(result.files)} 个文件：{request['out_dir']}")
        self.file_panel.load_directory(request["out_dir"])

    def run_merge_dialog(self) -> None:
        files = self.file_panel.selected_paths() or self.file_panel.paths()
        if len(files) < 2:
            self.toast.show_message("必须选定两个以上的文件来进行合并。", kind="error")
            return
        dialog = dialogs.MergeDialog(files, self.settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.result:
            return
        req = dialog.result
        try:
            out, count = splitter.merge_files(files, req["out_path"], req["add_title"],
                                              req["mode"], self.encoding, self.newline,
                                              req["delete_sources"])
        except OSError as exc:
            self.toast.show_message(f"合并失败：{exc}", kind="error")
            return
        self.toast.show_message(f"已合并 {count} 个文件：{out}")
        self.open_path(out)

    def run_zhconv(self) -> None:
        cursor = self.editor.textCursor()
        has_selection = cursor.hasSelection()
        source = cursor.selectedText().replace("\u2029", "\n") if has_selection else self.editor.toPlainText()
        menu = Menu(self)
        for label, mode in zhconv.CONVERT_MODES:
            action = menu.addAction(label)
            action.setData(mode)
        # 弹在触发按钮的正下方（命令栏按钮或工具菜单项），不能弹到窗口中部 ——
        # 原来用 mapToGlobal(rect().center())，菜单出现在屏幕中间，看着像错位。
        sender = self.sender()
        if isinstance(sender, QWidget) and sender.isVisible():
            pos = sender.mapToGlobal(QPoint(0, sender.height() + 4))
        else:
            pos = QCursor.pos()
        chosen = menu.exec(pos)
        if not chosen:
            return
        target = zhconv.convert(source, chosen.data())
        if has_selection:
            cursor.beginEditBlock()
            cursor.insertText(target)
            cursor.endEditBlock()
            self.modified = True
            self._update_title()
        else:
            # 整篇替换走统一入口：原写法在旧 cursor 上 beginEditBlock、
            # 却用 selectAll + 另一个 cursor 插入，编辑块没有真正包住插入，
            # 撤销时会被拆成两步（实测：一次 Ctrl+Z 只撤回一半）。
            self._replace_document_text(target)
        self.toast.show_message("简繁转换完成")

    def run_convert(self) -> None:
        name = self.convert_combo.currentData()
        paths = self.file_panel.selected_paths() or ([self.path] if self.path else [])
        paths = [p for p in paths if p]
        if not paths:
            self.toast.show_message("请先打开或选择要转换的文件。", kind="error")
            return
        if len(paths) == 1:
            result = convert_mod.convert(paths[0], name)
        else:
            result = convert_mod.convert_many(paths, name)
        if result.ok:
            # 规范 §七 ①：完成反馈走状态栏瞬时提示（详细清单进文件面板）
            self.toast.show_message(f"转换完成：{result.message}")
            if result.outputs:
                self.file_panel.add_files(result.outputs)
        else:
            self.toast.show_message(f"转换失败：{result.message}", kind="error")

    def run_goto(self) -> None:
        lines = self.editor.blockCount()
        dialog = dialogs.GotoDialog(lines, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        kind, value = dialog.value()
        if kind == "line":
            self.editor.go_to_line(value)
        else:
            self.editor.go_to_percent(value)

    def run_recode(self) -> None:
        dialog = dialogs.RecodeDialog(self.encoding, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        codec, newline = dialog.target()
        self.encoding = codec
        self.newline = newline
        self.modified = True
        self._update_title()
        self.toast.show_message(f"保存时将使用 {enc.ENCODING_LABELS.get(codec, codec)}")

    def open_settings(self) -> None:
        dialog = dialogs.OptionsDialog(self.settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings.save()
            self.setStyleSheet(stylesheet() + editor_font_qss(
                self.settings.font_family, self.settings.font_size, self.settings.line_height_percent))
            self.toast.show_message("选项已保存")

    def find_garbled(self) -> None:
        text = self.editor.toPlainText()
        spans = [(m.start(), m.end()) for m in
                 re.finditer(r"[\u00c0-\u00ff\u0100-\u02ff]{2,}|[\ufffd]{1,}", text)]
        if not spans:
            self.toast.show_message("未找到乱码！")
            return
        self._matches = spans
        self.editor.highlight_matches(spans, 0)
        self._select_match(0)
        self.toast.show_message(f"共找到 {len(spans)} 处疑似乱码，可用“修复选定乱码”尝试还原")

    def fix_garbled(self) -> None:
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            self.toast.show_message("先选定文件中的乱码，然后单击此按钮来修复。")
            return
        raw = cursor.selectedText()
        candidates: list[str] = []
        for src in ("latin-1", "cp1252"):
            try:
                candidates.append(raw.encode(src).decode("gb18030"))
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            try:
                candidates.append(raw.encode(src).decode("utf-8"))
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
        if not candidates:
            self.toast.show_message("无法识别该乱码的原始编码")
            return
        best = candidates[0]
        cursor.insertText(best)
        self.modified = True
        self._update_title()
        self.toast.show_message(f"已修复：{best[:20]}")

    # ---------------------------------------------------------------- 编辑动作
    def editor_undo(self) -> None:
        self.editor.undo()

    def editor_redo(self) -> None:
        self.editor.redo()

    def insert_text(self, text: str) -> None:
        self.editor.textCursor().insertText(text)

    def insert_date(self) -> None:
        self.insert_text(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def insert_filename(self) -> None:
        if self.path:
            self.insert_text(os.path.basename(self.path))

    def indent_selection(self, kind: str, direction: int) -> None:
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            unit = "\t" if kind == "tab" else ("　" if kind == "full" else " ")
            if direction > 0:
                cursor.insertText(unit * (self.settings.indent_count if kind != "tab" else 1))
            else:
                block_text = cursor.block().text()
                for unit in ("\t", "　", " "):
                    if block_text.startswith(unit):
                        pos = cursor.block().position()
                        sel = QTextCursor(self.editor.document())
                        sel.setPosition(pos)
                        sel.setPosition(pos + len(unit), QTextCursor.MoveMode.KeepAnchor)
                        sel.removeSelectedText()
                        break
            return
        unit = "\t" if kind == "tab" else ("　" if kind == "full" else " ")
        count = 1 if kind == "tab" else max(1, self.settings.indent_count)
        start_block = self.editor.document().findBlock(cursor.selectionStart())
        end_block = self.editor.document().findBlock(cursor.selectionEnd())
        cursor.beginEditBlock()
        block = start_block
        while block.isValid():
            edit = QTextCursor(block)
            edit.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            if direction > 0:
                edit.insertText(unit * count)
            else:
                line = block.text()
                for u in ("\t", "　", " "):
                    if line.startswith(u):
                        edit.setPosition(block.position())
                        edit.setPosition(block.position() + len(u), QTextCursor.MoveMode.KeepAnchor)
                        edit.removeSelectedText()
                        break
            if block == end_block:
                break
            block = block.next()
        cursor.endEditBlock()

    def strip_tail_spaces(self) -> None:
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText().replace("\u2029", "\n")
            cursor.insertText(punct.rstrip_lines(text))
            self.modified = True
            self._update_title()
        else:
            self._replace_document_text(punct.rstrip_lines(self.editor.toPlainText()))
        self.toast.show_message("已去除行尾空格")

    def change_case(self, mode: str) -> None:
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
            cursor.insertText(text.upper() if mode == "upper" else text.lower())
            self.modified = True
            self._update_title()
            return
        text = self.editor.toPlainText()
        self._replace_document_text(text.upper() if mode == "upper" else text.lower())

    def normalize_quotes(self) -> None:
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(punct.balance_quotes(cursor.selectedText()))
            self.modified = True
            self._update_title()
        else:
            self._replace_document_text(punct.balance_quotes(self.editor.toPlainText()))
        self.toast.show_message("首尾引号规范化完成")

    # ---------------------------------------------------------------- 视图
    def choose_font(self) -> None:
        from PySide6.QtGui import QFontDatabase
        from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                       QFontDialog, QPushButton)
        # 不用静态 getFont 而实例化对话框：要往里面加「恢复默认值」按钮，
        # 并把窗口撑大一点（原生尺寸偏小，用户提过）。
        # PySide6 的 getFont 返回 (ok, font)，和常见 PyQt 教程里的 (font, ok)
        # 正好相反 —— 按教程解包，点「确定」后 font 是个 bool，一调
        # .family() 就崩（实测 'bool' object has no attribute 'family'）。
        # 实例化 + exec() + selectedFont() 不经过那个坑。
        dialog = QFontDialog(QFont(self.settings.font_family, int(self.settings.font_size)), self)
        # 必须强制 Qt 自绘对话框：Windows 上 QFontDialog 可能走原生 ChooseFont
        # （Win32 ChooseFont），那样下面的自定义按钮和写作系统设置全都会失效。
        dialog.setOption(QFontDialog.FontDialogOption.DontUseNativeDialog)
        dialog.setWindowTitle("选择字体")
        dialog.resize(int(dialog.width() * 1.18) + 40, int(dialog.height() * 1.15) + 24)
        box = dialog.findChild(QDialogButtonBox)
        # 「书写系统」下拉是 QComboBox（实测不是 QFontComboBox，别找错类）
        ws_combo = dialog.findChild(QComboBox)
        if box is not None:
            def restore_default() -> None:
                # 出厂默认：简体中文 · 黑体 · 14 号（写作系统一并切过去，
                # 字体列表里才找得到黑体）
                if ws_combo is not None:
                    ws_combo.setCurrentIndex(
                        QFontDatabase.WritingSystem.SimplifiedChinese.value)
                dialog.setCurrentFont(QFont(DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE))

            btn = QPushButton("恢复默认值")
            box.addButton(btn, QDialogButtonBox.ButtonRole.ResetRole)
            btn.clicked.connect(restore_default)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        font = dialog.selectedFont()
        self.settings.font_family = font.family()
        # 选了点阵/位图字体时 pointSize 可能是 -1，别把字号打成负数
        self.settings.font_size = max(7, font.pointSize())
        # 只调这一个入口：它会 emit font_changed → _apply_editor_font_qss 刷新 QSS。
        # 原来这里还额外 setStyleSheet 一次，同一件事两条路径，改一处必漏另一处。
        self.editor.set_editor_font(self.settings.font_family, self.settings.font_size,
                                    self.settings.line_height_percent)

    def toggle_wrap(self, checked: bool) -> None:
        self.settings.word_wrap = checked
        self.editor.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if checked else QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff if checked else Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def toggle_statusbar(self, checked: bool) -> None:
        self.statusBar().setVisible(checked)

    def toggle_always_on_top(self, checked: bool) -> None:
        flags = self.windowFlags()
        if checked:
            self.setWindowFlags(flags | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowType.WindowStaysOnTopHint)
        self.show()

    def toggle_reading_mode(self, checked: bool) -> None:
        """菜单项“阅读模式”触发。"""
        self.apply_reading_mode(checked)

    def apply_reading_mode(self, enabled: bool) -> None:
        """阅读模式与整理模式的唯一入口（菜单、按钮、快捷键都走这里）。"""
        self.editor.set_reading_mode(enabled)
        self.mode_btn.setText("阅读模式" if enabled else "整理模式")
        self.mode_btn.setIcon(icons.icon("read" if enabled else "format", Color.text, 16))
        self.mode_btn.setToolTip("点击切换：阅读模式 ⇄ 整理模式")
        if self.mode_btn.isChecked() != enabled:
            self.mode_btn.setChecked(enabled)
        if self.act_reading.isChecked() != enabled:
            self.act_reading.blockSignals(True)
            self.act_reading.setChecked(enabled)
            self.act_reading.blockSignals(False)

    def _apply_editor_font_qss(self, family: str, size: float) -> None:
        """字号/字体变化时只刷新编辑区自己的样式。

        QSS 里的字号优先于 setFont，所以换字体必须同步刷新样式；
        但**不要对整个 MainWindow 调 setStyleSheet** —— 那会把全部控件
        重新 polish 一遍（Ctrl+= 连按几次就明显掉帧）。编辑区单独特化即可。
        字体也自此只有一条生效路径：editor.set_editor_font → font_changed → 这里。
        """
        self.editor.setStyleSheet(editor_font_qss(
            family, size, self.settings.line_height_percent))

    def toggle_auto_scroll(self, checked: bool) -> None:
        self.editor.set_auto_scroll(checked)

    def toggle_guide(self, checked: bool) -> None:
        self.editor.set_guide_column(40 if checked else 0)

    def zoom(self, direction: int) -> None:
        self.editor.zoom_by(0.5 * direction)

    def show_stats(self) -> None:
        text = self.editor.toPlainText()
        cursor = self.editor.textCursor()
        scope = cursor.selectedText() if cursor.hasSelection() else text
        chars = len(scope)
        cn = len(re.findall(r"[\u4e00-\u9fa5]", scope))
        lines = scope.count("\u2029") + 1 if cursor.hasSelection() else self.editor.blockCount()
        punct_count = len(re.findall(r"[，。！？；：、“”（）……—]", scope))
        # 规范 §七 ①：纯信息反馈走状态栏瞬时提示，不弹窗。
        # 状态栏一行放不下五项统计，明细同时复制到剪贴板。
        detail = (f"字符数：{chars}\n汉字数：{cn}\n行数：{lines}\n"
                  f"标点数：{punct_count}\n"
                  f"段落数：{len([p for p in re.split(r'[\\n\u2029]', scope) if p.strip()])}")
        QGuiApplication.clipboard().setText(detail)
        self.toast.show_message(
            f"统计：{chars} 字 / {cn} 汉字 / {lines} 行 / {punct_count} 标点"
            f" / {len([p for p in re.split(r'[\\n\u2029]', scope) if p.strip()])} 段"
            "　（明细已复制到剪贴板）")

    def show_about(self) -> None:
        dialogs.AboutDialog(self).exec()

    def copy_contact(self) -> None:
        """把作者邮箱复制到剪贴板（不打开邮件客户端，不跳转网页）。"""
        QGuiApplication.clipboard().setText(AUTHOR_EMAIL)
        self.toast.show_message(f"已复制邮箱 {AUTHOR_EMAIL}")

    # ================================================================ 杂项
