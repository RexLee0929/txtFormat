"""左侧文件列表面板与右侧“串替换”面板。"""

from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFontMetrics, QTextOption
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog,
                               QGridLayout, QHBoxLayout, QHeaderView, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPlainTextEdit, QSizePolicy,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import splitter
from . import icons
from .theme import Color
from .widgets import Caption, CommandButton, CompactComboBox, IconButton, SectionLabel


def human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} GB"


class MultiLineEdit(QPlainTextEdit):
    """可换行的输入框：固定显示两行内容，内容过长时自动折行。

    刻意保留 ``text()`` / ``setText()`` 两个 QLineEdit 风格的接口 ——
    调用方（主窗口、测试、正则库回填）都按单行框写，换成多行不该波及它们。
    回车插入换行；Ctrl+回车 发出 ``submitted``（用于"直接查找"）。

    **右侧不出现滚动条**：框高固定两行，长的正则靠折行 + 滚轮查看，
    避免右侧竖条把框挤窄、也让两个框看起来整齐一致。
    """

    submitted = Signal()

    def __init__(self, placeholder: str = "", rows: int = 2, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("role", "multiline-input")
        self.setPlaceholderText(placeholder)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)          # Tab 在输入框之间跳，不插制表符
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.set_rows(rows)

    def set_rows(self, rows: int) -> None:       # noqa: N802 - Qt 风格命名
        """按行数设定固定高度（含上下内边距与边框）。"""
        self._rows = max(1, rows)
        metrics = QFontMetrics(self.font())
        line = metrics.lineSpacing()
        self.setFixedHeight(line * self._rows + 6 * 2 + 6)

    # ---- QLineEdit 兼容接口
    def text(self) -> str:
        return self.toPlainText()

    def setText(self, value: str) -> None:          # noqa: N802 - Qt 命名
        self.setPlainText(value)

    def keyPressEvent(self, event):                 # noqa: N802 - Qt 命名
        """回车插入换行（多行编辑需要）；Ctrl+回车 直接触发查找。"""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


def human_time(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return "-"


class FilePanel(QWidget):
    """文件列表：目录、文件名、大小、日期，支持拖放与右键菜单。"""

    file_activated = Signal(str)
    files_changed = Signal()

    HEADERS = ("文件名", "大小", "修改日期", "创建日期")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._paths: list[str] = []
        self._directory = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(SectionLabel("文件目录"))

        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("选择或拖入文件夹 / txt 文件")
        self.dir_edit.setReadOnly(True)
        self.dir_edit.setMinimumHeight(32)
        dir_row.addWidget(self.dir_edit, 1)
        pick = IconButton("folder", "选择文件夹", size=32)
        pick.clicked.connect(self._pick_dir)
        dir_row.addWidget(pick)
        clear = IconButton("close", "清空列表", size=32)
        clear.clicked.connect(self.clear)
        dir_row.addWidget(clear)
        layout.addLayout(dir_row)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(56)
        for col, width in ((1, 54), (2, 78), (3, 78)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, width)
        self.table.doubleClicked.connect(self._on_double_click)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_menu)
        layout.addWidget(self.table, 1)

        self.summary = Caption("尚未选择文件")
        layout.addWidget(self.summary)

    # ------------------------------------------------------------ 目录
    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择文件所在目录", self._directory or "")
        if path:
            self.load_directory(path)

    def load_directory(self, path: str, recursive: bool = False) -> None:
        if os.path.isfile(path):
            self.add_files([path])
            return
        self._directory = path
        self.dir_edit.setText(path)
        self._paths.clear()
        try:
            names = sorted(os.listdir(path))
        except OSError:
            names = []
        for name in names:
            full = os.path.join(path, name)
            if os.path.isfile(full) and name.lower().endswith((".txt", ".log", ".ini", ".htm", ".html")):
                self._paths.append(full)
        self._refresh()

    def add_files(self, paths: list[str]) -> None:
        added = 0
        for path in paths:
            path = os.path.abspath(path)
            if os.path.isfile(path) and path not in self._paths:
                self._paths.append(path)
                added += 1
        if added:
            if not self._directory:
                self._directory = os.path.dirname(self._paths[0])
                self.dir_edit.setText(self._directory)
            self._refresh()

    def clear(self) -> None:
        self._paths.clear()
        self._directory = ""
        self.dir_edit.clear()
        self._refresh()

    # ------------------------------------------------------------ 刷新
    def _refresh(self) -> None:
        self.table.setRowCount(len(self._paths))
        total = 0
        for row, path in enumerate(self._paths):
            try:
                stat = os.stat(path)
                size = stat.st_size
                mtime = human_time(stat.st_mtime)
                ctime = human_time(stat.st_ctime)
            except OSError:
                size, mtime, ctime = 0, "-", "-"
            total += size
            name_item = QTableWidgetItem(os.path.basename(path))
            name_item.setIcon(icons.icon("file", Color.text_secondary, 16))
            name_item.setToolTip(path)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            self.table.setItem(row, 0, name_item)
            for col, text in enumerate((human_size(size), mtime, ctime), start=1):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                                      if col == 1 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)
        self.summary.setText(f"共 {len(self._paths)} 个文件，合计 {human_size(total)}" if self._paths else "尚未选择文件")
        self.files_changed.emit()

    # ------------------------------------------------------------ 交互
    def paths(self) -> list[str]:
        return list(self._paths)

    def selected_paths(self) -> list[str]:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        return [self._paths[r] for r in rows if 0 <= r < len(self._paths)]

    def _on_double_click(self, index) -> None:
        row = index.row()
        if 0 <= row < len(self._paths):
            self.file_activated.emit(self._paths[row])

    def _show_menu(self, pos) -> None:
        selected = self.selected_paths()
        menu = QMenu(self)
        if selected:
            act_open = QAction(icons.icon("open"), "打开", self)
            act_open.triggered.connect(lambda: self.file_activated.emit(selected[0]))
            menu.addAction(act_open)
            menu.addSeparator()
            menu.addAction(QAction(icons.icon("rename"), "文件更名…", self, triggered=self._rename_selected))
            menu.addAction(QAction(icons.icon("close"), "从列表移除（不删除文件）", self,
                                   triggered=self._remove_selected))
            menu.addAction(QAction(icons.icon("trash"), "删除文件…", self, triggered=self._delete_selected))
            menu.addSeparator()
            menu.addAction(QAction("删除文件名前面 3 个字符", self,
                                   triggered=lambda: self._rename_ops("prefix", 3)))
            menu.addAction(QAction("删除文件名中指定的字符串…", self,
                                   triggered=lambda: self._rename_ops("remove")))
            menu.addAction(QAction("删除某字符前的内容（含该字符）…", self,
                                   triggered=lambda: self._rename_ops("before")))
            menu.addAction(QAction("删除某字符后的内容（含该字符）…", self,
                                   triggered=lambda: self._rename_ops("after")))
            menu.addSeparator()
            menu.addAction(QAction("按文件名排序", self, triggered=self._sort_by_name))
            menu.addAction(QAction("按文件名中的数字排序", self, triggered=self._sort_by_number))
        else:
            menu.addAction(QAction(icons.icon("folder"), "选择文件夹…", self, triggered=self._pick_dir))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _sort_by_name(self) -> None:
        self._paths.sort(key=lambda p: os.path.basename(p).lower())
        self._refresh()

    def _sort_by_number(self) -> None:
        self._paths.sort(key=lambda p: splitter.natural_key(os.path.basename(p)))
        self._refresh()

    def _rename_selected(self) -> None:
        selected = self.selected_paths()
        if not selected:
            return
        from PySide6.QtWidgets import QInputDialog
        path = selected[0]
        old = os.path.basename(path)
        new, ok = QInputDialog.getText(self, "文件更名", "新的文件名：", QLineEdit.EchoMode.Normal, old)
        if ok and new.strip() and new != old:
            target = os.path.join(os.path.dirname(path), new.strip())
            try:
                os.rename(path, target)
                self.load_directory(os.path.dirname(path)) if self._directory else self._refresh()
            except OSError:
                pass

    def _remove_selected(self) -> None:
        for path in self.selected_paths():
            if path in self._paths:
                self._paths.remove(path)
        self._refresh()

    def _delete_selected(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        selected = self.selected_paths()
        if not selected:
            return
        if QMessageBox.question(self, "删除文件", "你确信要从磁盘中删除选定的文件吗？") != QMessageBox.StandardButton.Yes:
            return
        for path in selected:
            try:
                os.remove(path)
                self._paths.remove(path)
            except OSError:
                pass
        self._refresh()

    def _rename_ops(self, kind: str, count: int = 0) -> None:
        from PySide6.QtWidgets import QInputDialog
        selected = self.selected_paths()
        if not selected:
            return
        if kind == "prefix":
            count, ok = QInputDialog.getInt(self, "文件名规范化", "删除文件名前面的字符数：", 3, 0, 60)
            if not ok:
                return
            result = splitter.rename_strip_prefix(selected, count)
        else:
            title = {"remove": "删除文件名中指定的字符串：",
                     "before": "删除文件名中某字符前的内容（包含该字符）：",
                     "after": "删除文件名中某字符后的内容（包含该字符）："}[kind]
            text, ok = QInputDialog.getText(self, "文件名规范化", title)
            if not ok or not text:
                return
            func = {"remove": splitter.rename_remove_text,
                    "before": splitter.rename_cut_before,
                    "after": splitter.rename_cut_after}[kind]
            result = func(selected, text)
        if result.renamed:
            mapping = {old: new for old, new in result.renamed}
            self._paths = [mapping.get(p, p) for p in self._paths]
            self._refresh()

    # ------------------------------------------------------------ 拖放
    def dragEnterEvent(self, event):           # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):                # noqa: N802
        paths: list[str] = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                self.load_directory(path)
                return
            if os.path.isfile(path):
                paths.append(path)
        if paths:
            self.add_files(paths)
            event.acceptProposedAction()


class ReplacePanel(QWidget):
    """串替换面板：查找/替换/批量处理，与原程序布局一致。"""

    find_requested = Signal(str)               # forward
    find_prev_requested = Signal()
    replace_one_requested = Signal()
    replace_all_requested = Signal(bool)       # 仅选定区域
    library_selected = Signal(int)
    batch_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        layout.addWidget(SectionLabel("串替换"))

        self.find_edit = MultiLineEdit("查找内容（留空则用下方正则）", rows=2)
        self.find_edit.setToolTip("可直接粘贴较长的正则；内容过长时自动折行显示")
        layout.addWidget(self.find_edit)

        self.repl_edit = MultiLineEdit("替换为（留空表示删除）", rows=2)
        self.repl_edit.setToolTip("支持 $1 反引用；留空表示删除匹配内容")
        layout.addWidget(self.repl_edit)

        # 三个复选框各占一行：面板只有 300px 宽，横排会互相挤压
        self.regex_check = QCheckBox("使用正则表达式")
        self.regex_check.setChecked(True)
        self.regex_check.setToolTip("勾选后按正则表达式查找/替换，支持 $1 反引用")
        self.case_check = QCheckBox("区分大小写")
        self.batch_check = QCheckBox("批处理列表内所有文件")
        self.batch_check.setToolTip("只对带 * 的功能有效：直接改写文件列表里的每个文件")
        self.batch_check.toggled.connect(self.batch_toggled.emit)
        for box in (self.regex_check, self.case_check, self.batch_check):
            layout.addWidget(box)

        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(0, 2, 0, 0)

        def button(text: str, icon_name: str, slot, tip: str) -> CommandButton:
            btn = CommandButton(text, icon_name)
            btn.setProperty("compact", True)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            return btn

        self.btn_find = button("查找*", "search", lambda: self.find_requested.emit(self.find_edit.text()),
                               "从头查找并选中第一处匹配（支持批处理）")
        self.btn_prev = button("上一个", "prev", self.find_prev_requested.emit, "向上查找上一个匹配")
        self.btn_next = button("下一个", "next", lambda: self.find_requested.emit(self.find_edit.text()),
                               "向下查找下一个匹配")
        self.btn_replace = button("替换此处", "replace", self.replace_one_requested.emit,
                                  "只替换当前选中的这一处")
        self.btn_all = button("全部替换*", "replace", lambda: self.replace_all_requested.emit(False),
                              "替换全文中所有匹配（支持批处理）")
        self.btn_sel = button("替换选定", "replace", lambda: self.replace_all_requested.emit(True),
                              "只替换当前选中的区域内所有匹配")

        for col, btn in enumerate((self.btn_find, self.btn_prev, self.btn_next)):
            grid.addWidget(btn, 0, col)
        for col, btn in enumerate((self.btn_replace, self.btn_all, self.btn_sel)):
            grid.addWidget(btn, 1, col)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        layout.addLayout(grid)

        layout.addWidget(SectionLabel("常用正则表达式"),
                         alignment=Qt.AlignmentFlag.AlignLeft)
        # 常驻固定框：直接列出条目，点一下就套用，不用先展开下拉。
        # 下拉被去掉的原因有两个 —— 每展开一次的位置都不固定；面板下半部分是空的，
        # 没必要把内容藏进一个弹层里。框高按 rows 固定，条目多了用滚轮翻。
        self.library = QListWidget()
        self.library.setProperty("role", "regex-list")
        self.library.setUniformItemSizes(True)
        self.library.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.library.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.library.setToolTip("点选一条即套用到上面的查找/替换框")
        self._library_rows = 9
        self.library.setFixedHeight(24 * self._library_rows + 8)
        self.library.verticalScrollBar().setStyleSheet(
            "QScrollBar:vertical { width: 8px; margin: 2px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #D2D2D2; border-radius: 3px;"
            " min-height: 28px; }"
            "QScrollBar::handle:vertical:hover { background: #B4B4B4; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
            " { height: 0; width: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical"
            " { background: transparent; }")
        self.library.currentRowChanged.connect(self._on_library)
        layout.addWidget(self.library)

        self.note = Caption("")
        self.note.setStyleSheet(f"color: {Color.text_tertiary};")
        layout.addWidget(self.note)

        layout.addStretch(1)

    def _on_library(self, index: int) -> None:
        self.library_selected.emit(index)

    def populate(self, entries) -> None:
        """重新填充正则列表。第 0 行固定是「（不使用）」，与索引偏移对应。"""
        self.library.blockSignals(True)
        self.library.clear()
        self.library.addItem("（不使用）")
        for entry in entries:
            item = QListWidgetItem(entry.name)
            item.setToolTip(entry.note or entry.pattern)
            self.library.addItem(item)
        self.library.setCurrentRow(0)
        self.library.blockSignals(False)

    def current_library_index(self) -> int:
        return self.library.currentRow()

    def apply_entry(self, entry) -> None:
        self.find_edit.setText(entry.pattern)
        self.repl_edit.setText(entry.replacement)
        self.regex_check.setChecked(True)
        self.note.setText(entry.note or "")

    @property
    def use_regex(self) -> bool:
        return self.regex_check.isChecked()

    @property
    def ignore_case(self) -> bool:
        return not self.case_check.isChecked()

    @property
    def batch(self) -> bool:
        return self.batch_check.isChecked()


__all__ = ["FilePanel", "ReplacePanel", "MultiLineEdit", "human_size", "human_time"]
