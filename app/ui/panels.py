"""左侧文件列表面板与右侧“串替换”面板。"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QAction, QFontMetrics, QTextOption
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QGridLayout,
                               QHBoxLayout, QHeaderView, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QSizePolicy,
                               QTableWidget, QTableWidgetItem, QTableWidgetSelectionRange,
                               QVBoxLayout, QWidget)

from ..core import splitter
from . import icons
from .theme import Color
from .widgets import (Caption, CommandButton, ConfirmBar, IconButton, Menu,
                      SectionLabel)


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
        # 高度写死了，就别再参与垂直方向的伸缩 —— 否则面板高度紧张时
        # Qt 会在「该给列表的空间」和「这两个固定框」之间乱抢，
        # 把下方的正则列表挤扁（实测缩小窗口时列表最后一行被切）。
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

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
    #: 操作失败/部分失败的通知（重命名、删除）—— 由主窗口接到 Toast 上。
    #: 以前这些分支全是 ``except OSError: pass``，磁盘上什么都没发生、
    #: 界面也一声不吭，用户只能反复重试（「改了没反应」的一大来源）。
    notify = Signal(str)

    HEADERS = ("文件名", "大小", "修改日期", "创建日期")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._paths: list[str] = []
        self._seen: set[str] = set()      # 规范化后的路径，查重用（见 _norm）
        self._stat_cache: dict[str, tuple[tuple[int, int], str, str, str]] = {}
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

        # 内联输入条：更名 / 删除指定字符串都在这里输入，不弹模态 QInputDialog。
        # 模态框会把整个窗口挡住、和本程序「内联确认」的风格也不一致（规范 §七 ③）。
        self._prompt_row = QWidget()
        prompt_layout = QHBoxLayout(self._prompt_row)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        prompt_layout.setSpacing(6)
        self._prompt_label = Caption("")
        prompt_layout.addWidget(self._prompt_label)
        self._prompt_edit = QLineEdit()
        self._prompt_edit.setMinimumHeight(30)
        self._prompt_edit.returnPressed.connect(self._accept_prompt)
        self._prompt_edit.installEventFilter(self)
        prompt_layout.addWidget(self._prompt_edit, 1)
        prompt_ok = CommandButton("确定", "check")
        prompt_ok.clicked.connect(self._accept_prompt)
        prompt_layout.addWidget(prompt_ok)
        prompt_cancel = CommandButton("取消", "close")
        prompt_cancel.clicked.connect(self._cancel_prompt)
        prompt_layout.addWidget(prompt_cancel)
        self._prompt_row.hide()
        layout.addWidget(self._prompt_row)
        self._prompt_action: Callable[[str], None] | None = None

        # 内联确认条（规范 §七 ③：删文件不可逆，不弹模态框）
        self._pending_delete: list[str] = []
        self._delete_bar = ConfirmBar(self)
        self._delete_bar.confirmed.connect(self._do_delete)
        layout.addWidget(self._delete_bar)

    # ------------------------------------------------------------ 内联输入
    def _ask_inline(self, label: str, initial: str, on_ok: Callable[[str], None]) -> None:
        """在文件列表下方就地输入一行文本（替代 QInputDialog.getText）。"""
        self._prompt_action = on_ok
        self._prompt_label.setText(label)
        self._prompt_edit.setText(initial)
        self._prompt_row.show()
        self._prompt_edit.setFocus()
        self._prompt_edit.selectAll()

    def _cancel_prompt(self) -> None:
        self._prompt_action = None
        self._prompt_row.hide()

    def _accept_prompt(self) -> None:
        action = self._prompt_action
        text = self._prompt_edit.text().strip()
        self._prompt_action = None
        self._prompt_row.hide()
        if action is not None:
            action(text)

    def eventFilter(self, obj, event):        # noqa: N802 - Qt 命名
        # Esc 取消内联输入（与对话框行为一致）
        if obj is self._prompt_edit and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_prompt()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------ 目录
    @staticmethod
    def _norm(path: str) -> str:
        """查重用的规范化 key：abspath 只统一斜杠，不统一大小写 ——
        拖放/Qt 对话框给正斜杠、os.path.join 拼反斜杠、手输路径还可能小写盘符，
        同一个文件会以不同写法进来，按原样比较就查不到重（实测列表里
        同一个文件出现两行，磁盘上并没有第二个）。normcase 一并解决。"""
        return os.path.normcase(os.path.abspath(path))

    def _add_path(self, path: str) -> bool:
        key = self._norm(path)
        if key in self._seen:
            return False
        self._seen.add(key)
        self._paths.append(path)
        return True

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
        self._seen.clear()
        try:
            names = sorted(os.listdir(path))
        except OSError:
            names = []
        for name in names:
            full = os.path.join(path, name)
            if os.path.isfile(full) and name.lower().endswith((".txt", ".log", ".ini", ".htm", ".html")):
                self._add_path(full)
        self._refresh()

    def add_files(self, paths: list[str]) -> None:
        added = 0
        for path in paths:
            if os.path.isfile(path) and self._add_path(path):
                added += 1
        if added:
            if not self._directory:
                self._directory = os.path.dirname(self._paths[0])
                self.dir_edit.setText(self._directory)
            self._refresh()

    def clear(self) -> None:
        self._paths.clear()
        self._seen.clear()
        self._directory = ""
        self.dir_edit.clear()
        self._refresh()

    # ------------------------------------------------------------ 刷新
    def _row_texts(self, path: str) -> tuple[int, str, str, str]:
        """(字节数, 大小文本, 修改时间文本, 创建时间文本)，按 (mtime, size) 缓存。

        排序/删除一个文件都会重新刷新整表，每次都重新 stat + 格式化时间是白干 ——
        文件的 (mtime, size) 没变，显示文本就不会变。
        """
        try:
            stat = os.stat(path)
            size, mtime_ns = stat.st_size, stat.st_mtime_ns
        except OSError:
            return 0, "-", "-", "-"
        cached = self._stat_cache.get(path)
        if cached is not None and cached[0] == (mtime_ns, size):
            return size, cached[1], cached[2], cached[3]
        texts = (human_size(size), human_time(stat.st_mtime), human_time(stat.st_ctime))
        self._stat_cache[path] = ((mtime_ns, size), *texts)
        return size, *texts

    def _refresh(self) -> None:
        """按差异更新文件表：**不重建整张表**，并保留选中行。

        旧实现每次都 ``setRowCount`` + 每行新建 4 个 ``QTableWidgetItem``：
        500 个文件就是 2000 个对象反复分配，而且选中行每次都被清掉（排序一下、
        删掉一个文件，之前选的都白选了）。现在只补新增行、只改文本变了的单元格。
        """
        keep = set(self.selected_paths())
        total = 0
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(self._paths))
            for row, path in enumerate(self._paths):
                size, size_text, mtime_text, ctime_text = self._row_texts(path)
                total += size
                self._fill_row(row, path, size_text, mtime_text, ctime_text)
        finally:
            self.table.setUpdatesEnabled(True)
        self._restore_selection(keep)
        self.summary.setText(
            f"共 {len(self._paths)} 个文件，合计 {human_size(total)}" if self._paths else "尚未选择文件")
        self.files_changed.emit()

    def _fill_row(self, row: int, path: str, size_text: str,
                  mtime_text: str, ctime_text: str) -> None:
        """写一行；路径没变的行复用已有 item，只刷文本。"""
        name_item = self.table.item(row, 0)
        if name_item is None or name_item.data(Qt.ItemDataRole.UserRole) != path:
            name_item = QTableWidgetItem(os.path.basename(path))
            name_item.setIcon(icons.icon("file", Color.text_secondary, 16))
            name_item.setToolTip(path)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            self.table.setItem(row, 0, name_item)
        for col, text in enumerate((size_text, mtime_text, ctime_text), start=1):
            item = self.table.item(row, col)
            if item is None:
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    if col == 1 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)
            elif item.text() != text:
                item.setText(text)

    def _restore_selection(self, paths: set[str]) -> None:
        self.table.clearSelection()
        if not paths:
            return
        for row, path in enumerate(self._paths):
            if path in paths:
                self.table.setRangeSelected(QTableWidgetSelectionRange(row, 0, row, 3), True)

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
        # 用自绘 Menu（不透明窗口 + mask 圆角裁切），不能用原生 QMenu：QSS 给它
        # 圆角 8px 却没有 mask 处理，四个角会合成出黑色像素（与菜单栏弹层同款问题）。
        menu = Menu(self)
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
        path = selected[0]
        old = os.path.basename(path)

        def apply(new: str) -> None:
            if not new or new == old:
                return
            if os.path.basename(new) != new:      # 不许改名成别的目录
                self.notify.emit("文件名里不能带路径分隔符。")
                return
            target = os.path.join(os.path.dirname(path), new)
            try:
                os.rename(path, target)
            except OSError as exc:
                # 失败必须说出来（重名/占用/只读都会走这里），不能静默
                self.notify.emit(f"重命名失败：{exc}")
                return
            self._paths[self._paths.index(path)] = target
            self._seen = {self._norm(p) for p in self._paths}
            self._refresh()

        self._ask_inline("新的文件名：", old, apply)

    def _remove_selected(self) -> None:
        for path in self.selected_paths():
            if path in self._paths:
                self._paths.remove(path)
                self._seen.discard(self._norm(path))
        self._refresh()

    def _delete_selected(self) -> None:
        selected = self.selected_paths()
        if not selected:
            return
        # 规范 §七 ③：删文件不可逆，做内联确认条（不弹模态框）
        self._delete_bar.show_for(
            f"将从磁盘删除 {len(selected)} 个选定文件，不可撤销。",
            f"删除 {len(selected)} 个文件")
        self._pending_delete = list(selected)

    def _do_delete(self) -> None:
        selected = self._pending_delete
        self._pending_delete = []
        removed = 0
        failed: list[str] = []
        for path in selected:
            try:
                os.remove(path)
                self._paths.remove(path)
                self._seen.discard(self._norm(path))
                removed += 1
            except OSError as exc:
                failed.append(f"{os.path.basename(path)}（{exc.strerror or exc}）")
        self._refresh()
        if failed:
            # 部分失败也要说清楚是哪个文件 —— 否则用户以为全删了
            self.notify.emit(f"已删除 {removed} 个，{len(failed)} 个失败：" + "；".join(failed[:3]))

    def _rename_ops(self, kind: str, count: int = 0) -> None:
        selected = self.selected_paths()
        if not selected:
            return

        def apply_to_paths(result) -> None:
            if result.renamed:
                mapping = {old: new for old, new in result.renamed}
                self._paths = [mapping.get(p, p) for p in self._paths]
                self._seen = {self._norm(p) for p in self._paths}
                self._refresh()
            if result.skipped:
                self.notify.emit(f"{len(result.skipped)} 个文件未改名（无变化或改名失败）")

        if kind == "prefix":
            def apply_count(text: str) -> None:
                if not text.isdigit():
                    self.notify.emit("请输入一个正整数。")
                    return
                apply_to_paths(splitter.rename_strip_prefix(selected, int(text)))

            self._ask_inline("删除文件名前面的字符数：", str(count or 3), apply_count)
            return

        label = {"remove": "删除文件名中指定的字符串：",
                 "before": "删除文件名中某字符前的内容（包含该字符）：",
                 "after": "删除文件名中某字符后的内容（包含该字符）："}[kind]
        func = {"remove": splitter.rename_remove_text,
                "before": splitter.rename_cut_before,
                "after": splitter.rename_cut_after}[kind]

        def apply_text(text: str) -> None:
            if not text:
                return
            apply_to_paths(func(selected, text))

        self._ask_inline(label, "", apply_text)

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
    """替换规则（查找/替换）面板：查找/替换/批量处理，与原程序布局一致。"""

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
        # 标题与它下面的第一个控件之间只留 4px（原来统一 9px，用户反馈
        # 「标题与下面的框间隔太大」）；组与组之间再显式补 addSpacing。
        layout.setSpacing(4)

        layout.addWidget(SectionLabel("替换规则"))

        self.find_edit = MultiLineEdit("查找内容（留空则用下方正则）", rows=2)
        self.find_edit.setToolTip("可直接粘贴较长的正则；内容过长时自动折行显示")
        layout.addWidget(self.find_edit)

        self.repl_edit = MultiLineEdit("替换为（留空表示删除）", rows=2)
        self.repl_edit.setToolTip("支持 $1 反引用；留空表示删除匹配内容")
        layout.addWidget(self.repl_edit)

        layout.addSpacing(6)        # 输入区与开关区之间拉开一点

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
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        grid.setContentsMargins(0, 4, 0, 0)

        def button(text: str, slot, tip: str) -> CommandButton:
            # 纯文字 + 标准边框：原来的 subtle 无边框样式浮在面板里没有轮廓，
            # 再配上杂乱的小图标，整片看着散乱（用户反馈「有点丑」）。
            btn = CommandButton(text, "", kind="")
            btn.setProperty("compact", True)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            return btn

        self.btn_find = button("查找*", lambda: self.find_requested.emit(self.find_edit.text()),
                               "从头查找并选中第一处匹配（支持批处理）")
        self.btn_prev = button("上一个", self.find_prev_requested.emit, "向上查找上一个匹配")
        self.btn_next = button("下一个", lambda: self.find_requested.emit(self.find_edit.text()),
                               "向下查找下一个匹配")
        self.btn_replace = button("替换此处", self.replace_one_requested.emit,
                                  "只替换当前选中的这一处")
        self.btn_all = button("全部替换*", lambda: self.replace_all_requested.emit(False),
                              "替换全文中所有匹配（支持批处理）")
        self.btn_sel = button("替换选定", lambda: self.replace_all_requested.emit(True),
                              "只替换当前选中的区域内所有匹配")

        for col, btn in enumerate((self.btn_find, self.btn_prev, self.btn_next)):
            grid.addWidget(btn, 0, col)
        for col, btn in enumerate((self.btn_replace, self.btn_all, self.btn_sel)):
            grid.addWidget(btn, 1, col)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        layout.addLayout(grid)

        layout.addSpacing(6)        # 与上一组（按钮区）之间拉开一点
        layout.addWidget(SectionLabel("常用正则表达式"),
                         alignment=Qt.AlignmentFlag.AlignLeft)
        # 常驻固定框：直接列出条目，点一下就套用，不用先展开下拉。
        # 下拉被去掉的原因有两个 —— 每展开一次的位置都不固定；面板下半部分是空的，
        # 没必要把内容藏进一个弹层里。框高按 rows 固定，条目多了用滚轮翻。
        #
        # 高度是「上限固定 + 下限可收缩」的：窗口缩小时面板高度不够，
        # 若框高写死就会撑破面板、把下方的说明文字盖掉（实测缩小后错乱的
        # 主因）。这里给它一个下限，面板有富余时按上限显示、不够时按比例收缩。
        self.library = QListWidget()
        self.library.setProperty("role", "regex-list")
        self.library.setUniformItemSizes(True)
        self.library.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.library.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.library.setToolTip("点选一条即套用到上面的查找/替换框")
        self._library_rows = 12
        self._library_min_rows = 4
        self._row_height = 24
        self.library.setMinimumHeight(self._row_height * self._library_min_rows + 8)
        self.library.setMaximumHeight(self._row_height * self._library_rows + 8)
        self.library.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
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
        # 伸展因子给列表：面板有多余高度时列表长高（到上限为止），
        # 空间不够时列表按比例收缩到下限，绝不把别的控件挤出面板。
        layout.addWidget(self.library, 1)

        self.note = Caption("")
        self.note.setStyleSheet(f"color: {Color.text_tertiary};")
        layout.addWidget(self.note)
        # 底部弹簧：面板多出来的高度收到这里（说明文字贴住列表底部），
        # 否则剩余空间会分给说明文字，在列表和说明之间撑出一条空带。
        layout.addStretch(1)

    def _on_library(self, index: int) -> None:
        self.library_selected.emit(index)

    def resizeEvent(self, event):        # noqa: N802 - Qt 命名
        """把列表高度对齐到行高整数倍。

        高度不是行高整数倍时，最后一行会被切掉半截（实测缩小窗口时
        「查找 分隔线」只剩上半行）。这里按面板剩余空间自己算行数：
        列表高度永远 = 整数行 × 行高，绝不出现半行。
        """
        super().resizeEvent(event)
        self._align_library_rows()

    def showEvent(self, event):         # noqa: N802 - Qt 命名
        super().showEvent(event)
        self._align_library_rows()

    def _align_library_rows(self) -> None:
        """按面板剩余空间重算列表高度（行高整数倍）。"""
        lay = self.layout()
        others = 0
        for i in range(lay.count()):
            item = lay.itemAt(i)
            widget = item.widget()
            if widget is self.library:
                continue
            # addSpacing 产生的空白项没有 widget，但高度必须照算，
            # 否则列表会算出偏大的可用空间、把下方的说明文字顶出去
            if widget is not None:
                # 取 sizeHint 与 maximumHeight 中较小者：QPlainTextEdit 的
                # sizeHint 虚大（实际被 setFixedHeight 压到两行），直接用
                # sizeHint 会把可用空间算少、列表只剩保底 4 行（实测踩过）。
                others += min(widget.sizeHint().height(), widget.maximumHeight())
            else:
                others += item.sizeHint().height()
        spacing = lay.spacing() * max(0, lay.count() - 1)
        avail = self.height() - others - spacing
        rows = max(self._library_min_rows,
                   min(self._library_rows, avail // self._row_height))
        target = rows * self._row_height + 8
        if self.library.height() != target:
            self.library.setFixedHeight(target)

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
