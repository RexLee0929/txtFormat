"""各类对话框：格式整理选项、章节整理/分割、合并/更名、快速审核、转到、重编码、关于。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox,
                               QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QRadioButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QTextEdit,
                               QVBoxLayout, QWidget)

from ..core import aboutmd
from ..core import chapter as chapter_mod
from ..core import checkers, encoding as enc
from ..core.settings import Settings
from ..core.version import APP_NAME, AUTHOR, AUTHOR_EMAIL
from . import icons
from .theme import ACCENT, Color, apply_dwm_chrome
from .task import start_task, task_running, wait_task
from .widgets import (Caption, CommandButton, CopyChip, IconButton, PrimaryButton,
                      SectionLabel)


#: 正文换行阈值（px）——**本程序自己定的上限，不是窗口宽的档位**（规范 §七.2）。
#: 依据：正文 12px 微软雅黑，一个汉字约 12px，一行 44 字 ≈ 528px；加卡片左右内边距
#: 20×2 = 568；再留一点余量给「标签 + 控件」两列，取 640。超过这个宽度眼睛就要
#: 左右扫行了，所以**让正文折行，而不是把窗口撑宽**。
WRAP_LIMIT = 640

#: 对话框最小宽度：够放「取消 + 一个动词按钮」，再窄按钮就会换行。
MIN_WIDTH = 320

#: 工具窗口的最小尺寸（§七.7 的 MinWidth / MinHeight 兜底，不按内容拟合）
TOOL_MIN_WIDTH = 620
TOOL_MIN_HEIGHT = 460

#: 多行输入框敢给的最小可用宽（px，约 22 个汉字）：再窄一行字都写不满，
#: 输入长正则时看不到全局。内容由用户输入、量不出来，只能按「能用」兜底。
TEXT_FIELD_MIN_WIDTH = 380


class BaseDialog(QDialog):
    """对话框基类（规范 §七.2：主窗口的延续，不另立样式）。

    * **DWM 标题栏与主窗口同一套**（caption = #F3F3F3）—— 对话框不再是
      「另一种标题栏」；
    * **宽度按内容算、NoResize、高度按内容拟合**：打开时量出「最长的一行不可断
      内容」，内容短就窄回去，内容长就变宽（到 :data:`WRAP_LIMIT` 就让正文折行）。
      子类**不许**再往构造参数里传宽度死数 —— 那正是「所有框统一写死」的来源；
    * 行内提示出现/消失时高度跟着重算，内容不会被截。

    工具窗口（内容是反复改的表 / 列表）不要继承本类，走 :class:`ToolDialog`：
    那类窗口可拉伸、宽度归用户，与这里的 NoResize 是两套口径（规范 §七.7）。
    """

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 18, 20, 18)
        self.root.setSpacing(14)
        self._notice: QLabel | None = None
        self._fitted = False

    # ---------------------------------------------------------------- 尺寸
    def showEvent(self, event):                # noqa: N802 - Qt 命名
        super().showEvent(event)
        # 句柄建好才能做 DWM 定制（过早调用拿不到有效 hwnd）
        apply_dwm_chrome(int(self.winId()))
        self.fit_content()

    def natural_width(self) -> int:
        """量「最长的**一行**不可断内容」（规范 §七.2）。

        不能直接用 ``QLayout.sizeHint()``：带 ``wordWrap`` 的 QLabel、以及
        ``QTextBrowser``/表格这类控件给的 Preferred 宽普遍偏小，实测会让每个框
        都掉到下限 320（短句和长段一样宽 —— 那就又变成"写死"了）。

        这里按行量：硬换行拆开，逐行取 ``horizontalAdvance`` 的最大值；整段没有
        硬换行的长说明自然量出一个很大的数，会被 :data:`WRAP_LIMIT` 夹住、
        让正文折行 —— 这正是「上限是换行阈值，不是窗口档位」的意思。
        """
        # 卡片左右内边距（root margins 20×2）：文本宽加上它才是窗口该有的宽
        pad = 40
        need = self.root.sizeHint().width()

        for label in self.findChildren(QLabel):
            text = label.text()
            if not text:
                continue
            fm = label.fontMetrics()
            line_w = max(fm.horizontalAdvance(line) for line in text.split("\n"))
            need = max(need, line_w + pad)

        # 富文本正文（关于框）：按整篇不折行的理想宽算，再交给上限夹住
        for browser in self.findChildren(QTextBrowser):
            doc = browser.document()
            if doc is not None:
                doc.setTextWidth(-1)            # -1 = 不限宽，让 idealWidth 反映真实排版
                need = max(need, int(doc.idealWidth()) + pad)

        # 列表 / 表格：按**实际内容**量（列表取最宽那一项，表格取列宽之和）。
        # 它们的 Preferred 宽基本是个固定小值，不按内容量的话「文件合并」会挤成 334。
        for view in self.findChildren(QListWidget):
            need = max(need, view.sizeHintForColumn(0) + 28 + pad)   # 28 = 图标列 + 边距
        for table in self.findChildren(QTableWidget):
            cols = sum(table.columnWidth(i) for i in range(table.columnCount()))
            need = max(need, cols + 24 + pad)

        # 多行输入框：内容由用户输入，按「能用」的下限兜住（约 22 个汉字），
        # 再窄一行字都写不满，输入长正则会看不到全局。
        # （findChildren 只接受单个类型，不能传元组）
        for edit in self.findChildren(QPlainTextEdit) + self.findChildren(QTextEdit):
            need = max(need, TEXT_FIELD_MIN_WIDTH + pad)

        return need

    def fit_content(self) -> None:
        """按内容定宽 + 按内容拟合高度（规范 §七.2 的两条一起做）。

        顺序不能反：**先定宽再算高** —— 带 ``wordWrap`` 的 QLabel 高度依赖宽度，
        先按窄宽度算高会把「两行」永久记下来，窗口底部凭空多一条空带。
        """
        # 上一轮 setFixedWidth 把 min/max 都钉住了，不先放开就量不出新的自然宽
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)          # QWIDGETSIZE_MAX
        self.root.activate()

        width = max(MIN_WIDTH, min(self.natural_width(), WRAP_LIMIT))
        self.setFixedWidth(width)

        self.root.activate()
        # heightForWidth 在「没有可折行子项」的布局上返回 **-1**（不是 0），
        # 写成 `hfw or sizeHint()` 会把 -1 当真值、窗口高度变成 0（实测「转到」
        # 「重编码」两个框直接塌成一条线）。必须显式判 > 0。
        hfw = self.root.heightForWidth(width)
        height = hfw if hfw > 0 else self.root.sizeHint().height()
        self.setFixedHeight(height)
        self._fitted = True

    def refit(self) -> None:
        """内容增删后只重算**高度**。

        宽度在打开那一刻量好就固定：行内提示（:meth:`notice`）出现/消失时若连宽度
        一起重算，用户眼前的框会突然变宽变窄 —— 那是抖动，不是「按内容」。
        """
        if not self._fitted:
            return
        width = self.width()
        hfw = self.root.heightForWidth(width)
        self.setFixedHeight(hfw if hfw > 0 else self.root.sizeHint().height())

    # ---------------------------------------------------------------- 行内提示
    def notice(self, text: str = "", kind: str = "info") -> None:
        """页内提示（规范 §七 ②：行内提示 / 错误）。

        凡是「知道了就行」的反馈都用它，不弹窗：

        * ``kind="info"`` —— 成功/完成，灰色一行文字；
        * ``kind="error"`` —— 出错，警示色（#9D5D00）文字。

        提示区固定在按钮栏**上面**，不占正文位置；连续调用只更新文字，
        不会把版面顶来顶去。
        """
        if self._notice is None:
            self._notice = QLabel("")
            self._notice.setWordWrap(True)
            self._notice.setStyleSheet(
                f"color: {Color.text_secondary}; font-size: 12px;")
            # 插到按钮栏（root 最后一项）之前
            self.root.insertWidget(self.root.count() - 1, self._notice)
        self._notice.setText(text)
        color = Color.warning if kind == "error" else Color.text_secondary
        self._notice.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._notice.setVisible(bool(text))
        # 提示出现/消失会改变内容高度，窗口高度跟着重算（NoResize 下内容不能被截）
        self.refit()

    def add_footer(self, ok_text: str, cancel_text: str = "取消") -> QHBoxLayout:
        """按钮栏（规范 §七.3：主按钮必须是**动词短语**，把后果写进去）。

        ``ok_text`` **故意不给默认值** —— 曾经的默认「确定」会被新对话框顺手带进来，
        而「确定」不说明点了会发生什么（规范原文就写着「确定」→「删除 3 个文件」）。
        必填之后，漏写会在第一次打开对话框时直接报错，而不是悄悄多出一个「确定」。

        ``cancel_text`` 保留默认「取消」：取消的语义固定，不需要每个对话框各写一遍；
        传空串表示不要次按钮（只剩一个主按钮）。
        """
        row = QHBoxLayout()
        row.addStretch(1)
        if cancel_text:
            cancel = QPushButton(cancel_text)
            cancel.clicked.connect(self.reject)
            row.addWidget(cancel)
        ok = PrimaryButton(ok_text)
        ok.clicked.connect(self.accept)
        ok.setDefault(True)
        row.addWidget(ok)
        self.root.addLayout(row)
        return row


class ToolDialog(BaseDialog):
    """工具窗口（规范 §七.7）：内容是**反复改的表 / 列表** —— 可拉伸，宽度归用户。

    与 §七.2 的对话框是**两套口径，不叠加**：这里既不做 ``setFixedWidth``，也不按
    内容拟合高度，只给 MinWidth / MinHeight 兜住排版；首帧按内容给一个合适的初始
    尺寸，之后用户爱拉多大拉多大（表格要拖宽才看得见更多列）。

    判据（先判本节，再判 §七.2）：**内容是一张要反复改的表 / 列表 → 本文具窗口；
    只是一句话的确认或说明 → :class:`BaseDialog`。** 判成对话框的窗口不许用这套
    来回避拟合 —— 那正是「该拟合的不拟合」。
    """

    def showEvent(self, event):                # noqa: N802 - Qt 命名
        # 直接跳过 BaseDialog.showEvent：它会把窗口 setFixedSize 钉死，
        # 工具窗口一旦被钉住就再也拉不动（表格型窗口的命门）。
        QDialog.showEvent(self, event)
        apply_dwm_chrome(int(self.winId()))
        if self._fitted:
            return
        self._fitted = True
        # 首帧按内容给一个起点，但**不锁定**：下限由 MinWidth/MinHeight 兜住，
        # 上限由屏幕兜住（表格的自然宽可能比屏幕还宽，撑出去就点不到按钮了）。
        hint = self.root.sizeHint()
        screen = self.screen()
        avail = screen.availableGeometry() if screen is not None else None
        max_w = int(avail.width() * 0.82) if avail else 1280
        max_h = int(avail.height() * 0.82) if avail else 900
        self.setMinimumSize(min(TOOL_MIN_WIDTH, max_w), min(TOOL_MIN_HEIGHT, max_h))
        self.resize(min(max(hint.width(), TOOL_MIN_WIDTH), max_w),
                    min(max(hint.height(), TOOL_MIN_HEIGHT), max_h))

    def refit(self) -> None:
        """工具窗口的尺寸归用户：内容增删**不重排窗口**，免得刚拉好的大小被抢走。"""

    def keyPressEvent(self, event):            # noqa: N802 - Qt 命名
        """Esc 关闭；但焦点在输入框里时先让输入框失焦，不直接关窗。

        规范 §七.7：打字打到一半按 Esc 就把窗口关掉，是这个体型最常见的误伤。
        """
        if event.key() == Qt.Key.Key_Escape:
            focus = self.focusWidget()
            if isinstance(focus, (QLineEdit, QSpinBox, QComboBox)):
                focus.clearFocus()
                return
        super().keyPressEvent(event)


def _radio_group(options: list[tuple[str, str]], current: str, on_change) -> tuple[QWidget, dict[str, QRadioButton]]:
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(14)
    group = QButtonGroup(box)
    buttons: dict[str, QRadioButton] = {}
    for label, value in options:
        rb = QRadioButton(label)
        rb.setChecked(value == current)
        rb.toggled.connect(lambda checked, v=value: checked and on_change(v))
        group.addButton(rb)
        buttons[value] = rb
        layout.addWidget(rb)
    layout.addStretch(1)
    return box, buttons


# ------------------------------------------------------------------ 选项
class OptionsDialog(BaseDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__("格式整理选项", parent)
        self.settings = settings

        self.root.addWidget(SectionLabel("格式整理选项"))
        self.root.addWidget(Caption("这些设置直接决定“格式整理”按钮的处理结果，也影响 Tab / Shift+Tab 的缩进效果。"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        row = 0

        def add_row(label: str, widget: QWidget) -> None:
            nonlocal row
            lab = QLabel(label)
            lab.setMinimumWidth(110)
            grid.addWidget(lab, row, 0, Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(widget, row, 1)
            row += 1

        punct_widget, _ = _radio_group(
            [("转换为全角", "full"), ("转换为半角", "half"), ("不转换（保持原样）", "keep")],
            settings.punct_mode, lambda v: setattr(settings, "punct_mode", v))
        add_row("标点符号处理", punct_widget)

        eng_widget, _ = _radio_group(
            [("转换为全角", "full"), ("转换为半角", "half"), ("不转换", "keep")],
            settings.english_mode, lambda v: setattr(settings, "english_mode", v))
        add_row("英文字符处理", eng_widget)

        num_widget, _ = _radio_group(
            [("转换为全角", "full"), ("转换为半角", "half"), ("不转换", "keep")],
            settings.number_mode, lambda v: setattr(settings, "number_mode", v))
        add_row("数值处理", num_widget)

        para_widget, _ = _radio_group(
            [("隔一行", "blank"), ("不隔行", "none"), ("不处理（保持原样）", "keep")],
            settings.para_spacing, lambda v: setattr(settings, "para_spacing", v))
        add_row("段落间的隔行处理", para_widget)

        indent_widget, _ = _radio_group(
            [("半角空格", "half"), ("全角空格", "full"), ("制表符", "tab"), ("无缩进", "none")],
            settings.indent_kind, lambda v: setattr(settings, "indent_kind", v))
        add_row("行首缩进", indent_widget)

        indent_row = QWidget()
        indent_layout = QHBoxLayout(indent_row)
        indent_layout.setContentsMargins(0, 0, 0, 0)
        indent_layout.setSpacing(8)
        self.indent_spin = QSpinBox()
        self.indent_spin.setRange(0, 10)
        self.indent_spin.setValue(settings.indent_count)
        self.indent_spin.valueChanged.connect(lambda v: setattr(settings, "indent_count", v))
        indent_layout.addWidget(self.indent_spin)
        indent_layout.addWidget(QLabel("个"))
        indent_layout.addStretch(1)
        add_row("缩进个数", indent_row)

        width_row = QWidget()
        width_layout = QHBoxLayout(width_row)
        width_layout.setContentsMargins(0, 0, 0, 0)
        width_layout.setSpacing(8)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(10, 255)
        self.width_spin.setValue(settings.hard_return_width)
        self.width_spin.valueChanged.connect(lambda v: setattr(settings, "hard_return_width", v))
        width_layout.addWidget(self.width_spin)
        width_layout.addWidget(QLabel("字（10–255）"))
        width_layout.addStretch(1)
        add_row("去掉硬回车时的行宽", width_row)

        self.root.addLayout(grid)

        checks = QGridLayout()
        checks.setHorizontalSpacing(16)
        checks.setVerticalSpacing(6)
        self._checks: dict[str, QCheckBox] = {}
        options = [
            ("auto_hard_return", "自动处理硬回车"),
            ("has_ad", "文档中包含有广告"),
            ("split_by_period", "以句号为段落标记重新分段"),
            ("remove_spaces_in_text", "除去非标题行中的空格"),
            ("convert_unicode_code", "把 Unicode 码转成汉字"),
            ("restore_screened", "还原屏蔽码（如“少*妇”）"),
            ("restore_pinyin", "还原拼音（如“sè”）"),
            ("fix_punct_combo", "规范不合法的标点组合"),
            ("recursive", "处理子目录中的文件"),
            ("sort_by_number", "按文件名中的数字排序"),
        ]
        for i, (key, label) in enumerate(options):
            cb = QCheckBox(label)
            cb.setChecked(bool(getattr(settings, key)))
            cb.toggled.connect(lambda v, k=key: setattr(settings, k, v))
            if key == "convert_unicode_code":
                cb.setToolTip("把文档中形如 &#29234; / &#x7232; 的字符引用还原成汉字")
            elif key == "restore_screened":
                cb.setToolTip("把“少*妇”“成*人”这类被星号屏蔽的词还原，词表见 data/screened.txt")
            elif key == "restore_pinyin":
                cb.setToolTip("把“sè”“xìng”这类拼音还原成汉字，词表见 data/pinyin.txt")
            self._checks[key] = cb
            checks.addWidget(cb, i % 5, i // 5)
        self.root.addLayout(checks)

        bottom = QHBoxLayout()
        reset = CommandButton("恢复默认设置", "refresh")
        reset.clicked.connect(self._reset)
        bottom.addWidget(reset)
        bottom.addStretch(1)
        self.root.addLayout(bottom)

        # 主按钮写动词（规范 §七.3）：按钮要说清点下去会发生什么
        self.add_footer("保存")

    def _reset(self) -> None:
        self.settings.reset_format_options()
        defaults = Settings()
        for key, cb in self._checks.items():
            cb.blockSignals(True)
            cb.setChecked(bool(getattr(defaults, key)))
            cb.blockSignals(False)
            setattr(self.settings, key, getattr(defaults, key))
        self.indent_spin.setValue(self.settings.indent_count)
        self.width_spin.setValue(self.settings.hard_return_width)
        # 规范 §七 ②：能用行内提示的就不弹窗
        self.notice("选项已恢复为默认值。")


# ------------------------------------------------------------------ 章节
class SplitDialog(ToolDialog):
    """文件分割 / 章节整理。"""

    def __init__(self, text: str, settings: Settings, parent: QWidget | None = None):
        super().__init__("文件分割 / 章节整理", parent)
        self.text = text
        self.settings = settings
        self.chapters: list[chapter_mod.Chapter] = []
        self.result_text: str = text
        self.split_requested: dict | None = None
        self.title_mode = "cn"

        self.root.addWidget(SectionLabel("文件分割 / 章节整理"))

        top = QGridLayout()
        top.setHorizontalSpacing(10)
        top.setVerticalSpacing(8)
        top.addWidget(QLabel("请输入新的文件名前缀"), 0, 0)
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("盘符、路径及扩展名不必输入")
        top.addWidget(self.prefix_edit, 0, 1, 1, 3)

        top.addWidget(QLabel("章节名正则表达式"), 1, 0)
        self.pattern_combo = QComboBox()
        self.pattern_combo.setEditable(True)
        for label, pattern in chapter_mod.CHAPTER_FORMATS:
            self.pattern_combo.addItem(f"{label}", pattern)
        self.pattern_combo.setMinimumHeight(32)
        self.pattern_combo.currentIndexChanged.connect(self._sync_pattern_text)
        self._sync_pattern_text()
        top.addWidget(self.pattern_combo, 1, 1, 1, 2)
        refresh = CommandButton("重新获取章节名", "refresh")
        refresh.clicked.connect(self.reload_chapters)
        top.addWidget(refresh, 1, 3)
        self.root.addLayout(top)

        self.chapter_summary = Caption("")
        self.root.addWidget(self.chapter_summary)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["章节标题", "章节大小", "顺序"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 92)
        self.table.horizontalHeaderItem(0).setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setColumnWidth(2, 78)
        self.root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        btn_norm = CommandButton("规范化章节标题", "format")
        btn_norm.clicked.connect(self._normalize_titles)
        btn_reorder = CommandButton("重排章节顺序", "list")
        btn_reorder.clicked.connect(self._reorder)
        btn_export = CommandButton("导出章节标题列表", "save")
        btn_export.clicked.connect(self._export_titles)
        btn_drop_name = CommandButton("删除选定章节名", "trash")
        btn_drop_name.clicked.connect(self._remove_names)
        btn_drop = CommandButton("删除选定章节", "trash")
        btn_drop.clicked.connect(self._remove_chapters)
        self.btn_remove = btn_drop          # 内联确认时按钮就地变形
        for b in (btn_norm, btn_reorder, btn_export, btn_drop_name, btn_drop):
            actions.addWidget(b)
        actions.addStretch(1)
        self.root.addLayout(actions)

        format_row = QHBoxLayout()
        format_row.setSpacing(10)
        format_row.addWidget(QLabel("章节名格式"))
        self.mode_cn = QRadioButton("中文")
        self.mode_num = QRadioButton("数字")
        self.mode_cn.setChecked(True)
        self.mode_cn.toggled.connect(self._on_mode)
        format_row.addWidget(self.mode_cn)
        format_row.addWidget(self.mode_num)
        format_row.addSpacing(20)
        format_row.addWidget(QLabel("分割后文件大小 (KB)"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 10240)
        self.size_spin.setValue(32)
        format_row.addWidget(self.size_spin)
        format_row.addStretch(1)
        self.root.addLayout(format_row)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(QLabel("分割后的文件保存位置"))
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("默认与源文件同目录")
        path_row.addWidget(self.out_edit, 1)
        pick = IconButton("folder", "选择目录", size=32)
        pick.clicked.connect(self._pick_dir)
        path_row.addWidget(pick)
        self.root.addLayout(path_row)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.mode_size = QRadioButton("按指定大小分割文件")
        self.mode_chapter = QRadioButton("按章节分割文件")
        self.mode_chapter.setChecked(True)
        foot.addWidget(self.mode_chapter)
        foot.addWidget(self.mode_size)
        foot.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        foot.addWidget(cancel)
        ok = PrimaryButton("分割")
        ok.clicked.connect(self._do_split)
        foot.addWidget(ok)
        self.root.addLayout(foot)

        self.reload_chapters()

    # ---- 数据
    def current_pattern(self) -> str:
        data = self.pattern_combo.currentData()
        return data if isinstance(data, str) and data else self.pattern_combo.currentText()

    def _sync_pattern_text(self) -> None:
        pattern = self.pattern_combo.currentData()
        if isinstance(pattern, str) and pattern:
            self.pattern_combo.setEditText(pattern)
            self.pattern_combo.lineEdit().setCursorPosition(0)

    def reload_chapters(self) -> None:
        self.chapters = chapter_mod.parse_chapters(self.result_text, self.current_pattern())
        self._fill_table()

    def _update_summary(self) -> None:
        if not self.chapters:
            self.chapter_summary.setText("未找到任何章节，请调整下面的“章节名正则表达式”后重新获取。")
            self.chapter_summary.setStyleSheet(f"color: {Color.warning};")
        else:
            chars = sum(c.char_count for c in self.chapters)
            suspects = sum(1 for c in self.chapters if c.suspect)
            text = f"章节数：{len(self.chapters)}　共 {chars} 字"
            if suspects:
                text += f"　其中 {suspects} 处章号不连续（已标红，请检查）"
            self.chapter_summary.setText(text)
            self.chapter_summary.setStyleSheet(f"color: {Color.text_secondary};")

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self.chapters))
        for row, ch in enumerate(self.chapters):
            title_item = QTableWidgetItem(ch.title)
            if ch.suspect:
                title_item.setForeground(Qt.GlobalColor.darkRed)
                title_item.setToolTip("章号与上一章不连续，请检查是否缺章、重复或章节名不规范")
            self.table.setItem(row, 0, title_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(ch.char_count)))
            order_item = QTableWidgetItem(ch.order_text)
            if ch.suspect:
                order_item.setForeground(Qt.GlobalColor.darkRed)
            self.table.setItem(row, 2, order_item)
        self._update_summary()

    def _selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def _on_mode(self, cn: bool) -> None:
        self.title_mode = "cn" if cn else "num"

    # ---- 操作
    def _normalize_titles(self) -> None:
        self.result_text, count = chapter_mod.normalize_titles(
            self.result_text, self.current_pattern(), self.title_mode)
        self.reload_chapters()
        self.notice(f"共规范化 {count} 个章节标题。")

    def _reorder(self) -> None:
        self.result_text, count = chapter_mod.renumber(
            self.result_text, self.current_pattern(), self.title_mode)
        self.reload_chapters()
        self.notice(f"已按列表顺序重新编号 {count} 处。")

    def _remove_names(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        for row in reversed(rows):
            if 0 <= row < len(self.chapters):
                ch = self.chapters[row]
                line_end = self.result_text.find("\n", ch.start)
                if line_end < 0:
                    line_end = len(self.result_text)
                self.result_text = self.result_text[:ch.start] + self.result_text[line_end + 1:]
        self.reload_chapters()

    def _remove_chapters(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        # 规范 §七 ③：不可逆操作做**内联确认**（按钮就地变「确认删除」），
        # 不弹模态框 —— 弹窗会把流程打断，用户连删的是哪几章都没看见。
        btn = self.btn_remove
        if not getattr(self, "_remove_armed", False):
            self._remove_armed = True
            btn.setText("确认删除")
            self.notice(f"将删除 {len(rows)} 个章节（含正文，不可撤销）。再点一次「确认删除」执行。")
            return
        self._remove_armed = False
        btn.setText("删除选定章节")
        spans = [(self.chapters[r].start, self.chapters[r].end) for r in rows if 0 <= r < len(self.chapters)]
        for start, end in sorted(spans, reverse=True):
            self.result_text = self.result_text[:start] + self.result_text[end:]
        self.reload_chapters()
        self.notice(f"已删除 {len(rows)} 个章节。")

    def _export_titles(self) -> None:
        default_dir = self.out_edit.text() or os.path.dirname(self.settings.last_dir or ".")
        path, _ = QFileDialog.getSaveFileName(self, "导出章节标题列表",
                                              os.path.join(default_dir, "ChapterList.txt"), "文本文件 (*.txt)")
        if not path:
            return
        content = "\n".join(f"{c.index}\t{c.title}\t{c.char_count}" for c in self.chapters)
        enc.save_text(path, content + "\n", "utf-8", "\n")
        # 记住本次落点，下次打开/另存为优先到这里（路径记忆统一写 last_dir）
        self.settings.last_dir = os.path.dirname(path)
        self.notice(f"导出完成，共写入章节名 {len(self.chapters)} 条。")

    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择分割后的文件所在目录",
                                                self.settings.last_dir or "")
        if path:
            self.out_edit.setText(path)
            self.settings.last_dir = path

    def _do_split(self) -> None:
        out_dir = self.out_edit.text().strip()
        if not out_dir:
            # 规范 §七 ②：出错写在页里，不弹窗
            self.notice("请先选择分割后的文件保存位置。", "error")
            return
        self.split_requested = {
            "out_dir": out_dir,
            "prefix": self.prefix_edit.text().strip(),
            "by_chapter": self.mode_chapter.isChecked(),
            "size_kb": self.size_spin.value(),
            "pattern": self.current_pattern(),
        }
        self.accept()


# ------------------------------------------------------------------ 合并
class MergeDialog(BaseDialog):
    def __init__(self, files: list[str], settings: Settings, parent: QWidget | None = None):
        super().__init__("文件更名 / 文件合并", parent)
        self.files = files
        self.settings = settings
        self.result: dict | None = None

        self.root.addWidget(SectionLabel("文件合并"))
        self.root.addWidget(Caption(f"将按列表顺序合并以下 {len(files)} 个文件：" if files else "请先在左侧列表中选择要合并的文件。"))

        self.list = QListWidget()
        for path in files:
            item = QListWidgetItem(icons.icon("file", Color.text_secondary, 16), os.path.basename(path))
            item.setToolTip(path)
            self.list.addItem(item)
        self.list.setMaximumHeight(200)
        self.root.addWidget(self.list)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.addWidget(QLabel("请输入新的文件名"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("盘符及路径不必输入")
        grid.addWidget(self.name_edit, 0, 1)

        grid.addWidget(QLabel("合并后的文件保存位置"), 1, 0)
        dir_row = QWidget()
        dir_layout = QHBoxLayout(dir_row)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(6)
        self.dir_edit = QLineEdit()
        if files:
            self.dir_edit.setText(os.path.dirname(files[0]))
        dir_layout.addWidget(self.dir_edit, 1)
        pick = IconButton("folder", "选择目录", size=32)
        pick.clicked.connect(self._pick_dir)
        dir_layout.addWidget(pick)
        grid.addWidget(dir_row, 1, 1)
        self.root.addLayout(grid)

        self.add_title_check = QCheckBox("添加文件名作为章节名")
        self.add_title_check.setChecked(True)
        self.delete_src_check = QCheckBox("合并后删除原文件")
        self.root.addWidget(self.add_title_check)
        self.root.addWidget(self.delete_src_check)

        self.mode_row = QWidget()
        mode_layout = QHBoxLayout(self.mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.addWidget(QLabel("章节名格式"))
        self.mode_cn = QRadioButton("中文")
        self.mode_num = QRadioButton("数字")
        self.mode_cn.setChecked(True)
        mode_layout.addWidget(self.mode_cn)
        mode_layout.addWidget(self.mode_num)
        mode_layout.addStretch(1)
        self.root.addWidget(self.mode_row)

        self.add_footer("合并")

    def _pick_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择合并后的文件保存位置",
                                                self.settings.last_dir or "")
        if path:
            self.dir_edit.setText(path)
            self.settings.last_dir = path

    def accept(self) -> None:
        directory = self.dir_edit.text().strip()
        name = self.name_edit.text().strip()
        if not directory or not name:
            self.notice("请填写文件名与保存位置。", "error")
            return
        if not name.lower().endswith(".txt"):
            name += ".txt"
        self.result = {
            "out_path": os.path.join(directory, name),
            "add_title": self.add_title_check.isChecked(),
            "delete_sources": self.delete_src_check.isChecked(),
            "mode": "cn" if self.mode_cn.isChecked() else "num",
        }
        super().accept()


# ------------------------------------------------------------------ 快速审核
REVIEW_ITEMS = [
    ("typos", "常见错别字"),
    ("dedi", "的得地误用"),
    ("punct", "不规则的标点符号"),
    ("quotes", "引号不匹配 / 嵌套引号"),
    ("brackets", "半个括号、括号不匹配"),
    ("pinyin", "拼音"),
    ("traditional", "繁体字"),
    ("longline", "超长段落（疑似缺标点）"),
]


class QuickReviewDialog(ToolDialog):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__("快速审核", parent)
        self.text = text
        self.issues: list[checkers.Issue] = []
        self._all: list[checkers.Issue] = []

        self.root.addWidget(SectionLabel("快速审核"))
        self.root.addWidget(Caption("勾选要检查的项目，单击“开始检查”。结果按出现顺序列出，双击可定位。"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        self._checks: list[tuple[str, QCheckBox]] = []
        for i, (key, label) in enumerate(REVIEW_ITEMS):
            cb = QCheckBox(label)
            cb.setChecked(key in ("typos", "punct", "quotes", "brackets"))
            grid.addWidget(cb, i % 4, i // 4)
            self._checks.append((key, cb))
        self.root.addLayout(grid)

        row = QHBoxLayout()
        start = PrimaryButton("开始检查", "check")
        start.clicked.connect(self._run)
        row.addWidget(start)
        row.addStretch(1)
        self.summary = Caption("")
        row.addWidget(self.summary)
        self.root.addLayout(row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["类型", "内容", "建议", "位置"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._goto_issue)
        self.root.addWidget(self.table, 1)

        closer = QPushButton("关闭")
        closer.clicked.connect(self.accept)
        self.root.addWidget(closer, 0, Qt.AlignmentFlag.AlignRight)

    def preselect(self, keys: set[str] | tuple[str, ...] | list[str]) -> None:
        """勾选指定检查器并立刻跑一遍（主窗口「一键审核」按正则库条目调过来）。

        对外公开的方法 —— 主窗口原来直接摸 ``dialog._checks`` 和 ``dialog._run()``，
        私有成员一改签名就崩，这种跨类耦合必须收进来。
        """
        wanted = set(keys)
        for key, cb in self._checks:
            cb.setChecked(key in wanted)
        self._run()

    def _run(self) -> None:
        """在后台线程跑检查（全文错别字/的得地/标点扫描是秒级的活）。

        以前这里同步跑：文档一大，点「开始检查」窗口就整段假死（连"取消"都点不动）。
        现在把选中的检查器丢到后台，跑完再回 UI 线程填表。
        """
        if task_running(self):
            return
        picked = [(key, cb) for key, cb in self._checks if cb.isChecked()]
        if not picked:
            self.notice("请至少勾选一项检查。", "error")
            return
        self.summary.setText("正在检查…")
        self.table.setRowCount(0)
        text = self.text

        def work():
            found: list[checkers.Issue] = []
            errors: list[str] = []
            for key, cb in picked:
                try:
                    found.extend(checkers.run_checker(key, text))
                except Exception as exc:                # noqa: BLE001 - 单个检查器出错不拖垮整轮
                    errors.append(f"{cb.text()}：{exc}")
            return found, errors

        def apply(result) -> None:
            self._all, errors = result
            # 规范 §七 ②：单个检查器出错写在页里，不弹窗（弹窗会把结果表盖住）
            if errors:
                self.notice("；".join(errors[:3]), "error")
            self._fill_table()

        def failed(message: str) -> None:
            self.summary.setText("")
            self.notice(f"检查失败：{message}", "error")

        start_task(self, work, apply, failed)

    def _fill_table(self) -> None:
        self._all.sort(key=lambda i: i.start)
        self.table.setRowCount(len(self._all))
        for row, issue in enumerate(self._all):
            self.table.setItem(row, 0, QTableWidgetItem(issue.kind))
            self.table.setItem(row, 1, QTableWidgetItem(issue.text[:60]))
            self.table.setItem(row, 2, QTableWidgetItem(issue.suggestion))
            self.table.setItem(row, 3, QTableWidgetItem(str(issue.start)))
        kinds = len({i.kind for i in self._all})
        self.summary.setText(f"共找到 {kinds} 类 / {len(self._all)} 处问题" if self._all else "未发现问题。")

    def closeEvent(self, event) -> None:                # noqa: N802 - Qt 命名
        # 后台检查没跑完就关窗会让 QThread 在运行中被析构（进程直接崩）
        wait_task(self, 3000)
        super().closeEvent(event)

    def _goto_issue(self, index) -> None:
        row = index.row()
        if 0 <= row < len(self._all):
            self.selected_offset = self._all[row].start
            self.accept()


# ------------------------------------------------------------------ 转到
class GotoDialog(BaseDialog):
    def __init__(self, max_line: int, parent: QWidget | None = None):
        super().__init__("转到", parent)
        self.root.addWidget(QLabel("跳转到："))
        self.line_radio = QRadioButton("行")
        self.percent_radio = QRadioButton("百分比")
        self.line_radio.setChecked(True)
        self.spin = QSpinBox()
        self.spin.setRange(1, max(1, max_line))
        self.spin.setValue(1)
        row = QHBoxLayout()
        row.addWidget(self.line_radio)
        row.addWidget(self.spin, 1)
        self.root.addLayout(row)
        prow = QHBoxLayout()
        prow.addWidget(self.percent_radio)
        self.percent = QSpinBox()
        self.percent.setRange(0, 100)
        self.percent.setSuffix(" %")
        prow.addWidget(self.percent, 1)
        self.root.addLayout(prow)
        self.line_radio.toggled.connect(lambda on: (self.spin.setEnabled(on), self.percent.setEnabled(not on),
                                                    self.percent.setValue(0)))
        self.percent.setEnabled(False)
        self.add_footer("转到")

    def value(self) -> tuple[str, int]:
        return ("line", self.spin.value()) if self.line_radio.isChecked() else ("percent", self.percent.value())


# ------------------------------------------------------------------ 重编码
class RecodeDialog(BaseDialog):
    def __init__(self, current: str, parent: QWidget | None = None):
        super().__init__("重编码", parent)
        self.root.addWidget(QLabel("目标编码："))
        self.combo = QComboBox()
        for label, codec in enc.ENCODINGS:
            self.combo.addItem(label, codec)
        self.combo.setMinimumHeight(32)
        index = self.combo.findData(current)
        if index >= 0:
            self.combo.setCurrentIndex(index)
        self.root.addWidget(self.combo)

        self.root.addWidget(QLabel("行尾格式："))
        self.newline = QComboBox()
        self.newline.addItem("DOS/Windows (CRLF)", "\r\n")
        self.newline.addItem("Unix (LF)", "\n")
        self.newline.addItem("Mac (CR)", "\r")
        self.newline.setMinimumHeight(32)
        self.root.addWidget(self.newline)
        self.add_footer("应用")

    def target(self) -> tuple[str, str]:
        return self.combo.currentData(), self.newline.currentData()


# ------------------------------------------------------------------ 关于
#
# 文案不写在这里（规范 §八）：全部放在 app/data/ABOUT.md，启动时读文件、
# 替换占位符、再渲成富文本。改一句介绍只改 md，不动代码、不重算窗口高度。


class AboutDialog(BaseDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("关于 " + APP_NAME, parent)
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(False)          # 不打开外部程序
        self._browser.setHtml(aboutmd.render(accent=ACCENT))
        self._browser.setStyleSheet(f"background: {Color.card}; border: 1px solid {Color.border};"
                                    f"border-radius: 8px; padding: 14px;")
        # 高度不写死（规范 §八）：showEvent 里按富文本真实高度拟合
        self.root.addWidget(self._browser)

        # ---- 联系方式：点击即复制，不跳转、不调用邮件客户端
        # 交互与 ComicConverter 的「关于」对话框同构：胶囊是唯一的复制入口，
        # 按钮栏只留「关闭」——复制成功时胶囊变强调色，右侧出现「已复制到剪贴板」，
        # 1.6 秒后自动恢复。不弹 tooltip 气泡（气泡会挡住下方内容）。
        box = QFrame()
        box.setObjectName("ContactBox")
        box.setStyleSheet(f"#ContactBox {{ background: {Color.card_alt};"
                          f"border-radius: 8px; }}")
        row = QHBoxLayout(box)
        row.setContentsMargins(14, 9, 14, 9)
        row.setSpacing(10)
        who = QLabel(f"作者  {AUTHOR}")
        who.setStyleSheet(f"color: {Color.text_secondary}; font-size: 12px;")
        row.addWidget(who)
        self.chip = CopyChip(AUTHOR_EMAIL, hint="点击复制邮箱")
        row.addWidget(self.chip)
        # 平时为空；点击复制后在这里显示「已复制到剪贴板」，1.6 秒后自动消失
        self.hint = Caption("")
        self.hint.setStyleSheet(f"color: {Color.text_tertiary}; font-size: 11px;")
        row.addWidget(self.hint)
        row.addStretch(1)
        self.root.addWidget(box)

        self._hint_timer = QTimer(self)
        self._hint_timer.setSingleShot(True)
        self._hint_timer.timeout.connect(lambda: self.hint.setText(""))
        self.chip.copied.connect(self._on_copied)

        footer = QHBoxLayout()
        footer.addStretch(1)
        close_btn = PrimaryButton("关闭")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        self.root.addLayout(footer)

    def showEvent(self, event):                # noqa: N802 - Qt 命名
        super().showEvent(event)
        # 宽度定下来后按富文本真实高度拟合（规范 §八：高自动拟合、不写死、
        # 不出现窗口级滚动条）。document().size() 在布局后测量，下一轮事件再收敛一次。
        self.setFixedWidth(self.width())
        self._fit_height()
        QTimer.singleShot(0, self._fit_height)

    def _fit_height(self) -> None:
        doc_h = self._browser.document().size().height()
        # +30 = 卡片内边距 14×2 + 边框/圆角余量
        self._browser.setFixedHeight(max(120, int(doc_h) + 30))
        self.setFixedHeight(self.sizeHint().height())

    def _on_copied(self, value: str) -> None:
        """复制结果的反馈：胶囊已变色，这里补一句右侧提示。"""
        if value:
            self.hint.setStyleSheet(f"color: {ACCENT}; font-size: 11px;")
            self.hint.setText("已复制到剪贴板")
        else:
            self.hint.setStyleSheet(f"color: {Color.text_tertiary}; font-size: 11px;")
            self.hint.setText("复制失败，请手动选中邮箱文字复制")
        self._hint_timer.start(1600)


__all__ = ["OptionsDialog", "SplitDialog", "MergeDialog", "QuickReviewDialog",
           "GotoDialog", "RecodeDialog", "AboutDialog", "BaseDialog", "ToolDialog",
           "REVIEW_ITEMS", "WRAP_LIMIT", "MIN_WIDTH"]
