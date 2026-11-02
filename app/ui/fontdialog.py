"""自绘字体对话框（规范 §七.2：对话框是主窗口的延续）。

历史：最早用 Qt 内置 ``QFontDialog``（英文标签、系统配色、可拉伸），后来换成
``QFontComboBox``——但它的弹层是 **Qt 自己的 QFontListView**：每条前面一个红色
「TT」图标、后面拖一句「中文范例」，弹层方角通到边、宽度随意，和这套自绘界面
一眼两族。现在整个重做成与主窗口同一套语言的**字体选择器**：

* 上方搜索框（``SearchBox``，与主窗口搜索框同款）实时过滤——字体多的机器上
  滚几百条找「宋体」是上一版最难受的地方；
* 左侧字体列表：**每条用该字体自身渲染族名**（选之前就能看出字形），无图标、
  无样张后缀，行高统一；
* 右侧：字号（带「号」后缀）+ 字重（常规/中黑/加粗）+ 斜体 + 行距%
  + 大预览卡 + 当前选择摘要；
* 双击条目 / 回车 = 确定；
* 「恢复默认值」= 程序的实际默认（:class:`app.core.settings.Settings` 的
  ``font_family`` / ``font_size``，默认值只在这一处定义，对话框不写第二份）。

弹层风格约束见 :class:`app.ui.widgets.SearchBox` 与 ``CompactComboBox``：输入控件
一律白底、1px 边框、4px 圆角，聚焦时强调色下边线，不出现 Qt 原生控件外观。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QSizePolicy,
                               QVBoxLayout)

from ..core.settings import Settings
from .dialogs import BaseDialog
from .theme import Color
from .widgets import CompactComboBox, PrimaryButton, SearchBox

#: 程序默认字体（「恢复默认值」用）—— 引用 Settings 的字段，不写第二份：
#: 以前这里写死「黑体 14」，和 Settings 里的实际默认（雅黑 UI 12）对不上，
#: 点「恢复默认值」反而把用户改到和首次启动不一样的字体。
DEFAULT_FONT_FAMILY = Settings.font_family
DEFAULT_FONT_SIZE = Settings.font_size

#: 字重档位（显示文案 → QFont weight 数值）。雅黑有 Light/Regular/Bold 三档
#: 实字重；中黑 500 会由 Qt 挑最接近的已有字重，不会生造。
WEIGHTS: tuple[tuple[str, int], ...] = (("常规", 400), ("中黑", 500), ("加粗", 700))

#: 预览样张：中英混排 + 数字，能同时看出中西文是否同一族
SAMPLE = "中文示例　AaBbYyZz　0123"

#: 字体列表里每条的显示字号（族名用自身字体渲染）
LIST_POINT_SIZE = 10

#: 参数区四个控件的统一宽度。**弹层宽度也跟着这个值走**（CompactComboBox
#: 的弹层宽 = max(控件宽, 最宽项 + 内边距)）—— 字段与弹层同宽，弹层就永远
#: 落在字段正下方，不会横向溢出到别的控件上（用户报过「字重选项框超出去」）。
FIELD_WIDTH = 104

#: 字号档位（常用正文/标题号数；配置里的散值会自动补进来）
SIZE_CHOICES: tuple[int, ...] = (8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20,
                                 22, 24, 28, 32, 36, 42, 48, 56, 64, 72, 96)

#: 行距档位（%，100 = 单倍）
LINE_CHOICES: tuple[int, ...] = (100, 110, 120, 130, 140, 150, 160, 170,
                                 180, 200, 220, 250, 280, 300)


def _value_combo(choices: tuple[int, ...], current: int,
                 suffix: str) -> CompactComboBox:
    """把一个数值参数做成下拉框：内置档位 + 当前值（不在档位里就插进去）。"""
    values = list(choices)
    if current not in values:
        values.append(current)
        values.sort()
    box = CompactComboBox(rows=8)
    for value in values:
        box.addItem(f"{value}{suffix}", value)
    box.setFixedWidth(FIELD_WIDTH)
    box.setCurrentIndex(values.index(current))
    return box


class FontDialog(BaseDialog):
    """选择字体：搜索 + 字体族列表 + 字号/字重/斜体/行距 + 实时预览。"""

    def __init__(self, family: str, size: int, weight: int = 400,
                 italic: bool = False, line_percent: int = 160, parent=None):
        super().__init__("选择字体", parent)

        # 记下传入的族名：字体库为空（离屏模式）或该字体已卸载时，列表里找不到
        # 它，仍要能原样返回原字体。
        self._fallback_family = family or DEFAULT_FONT_FAMILY

        # ---------------------------------------------------------- 搜索框
        self.search = SearchBox("搜索字体…")
        self.search.textChanged.connect(self._filter)
        self.root.addWidget(self.search)

        # ---------------------------------------------------------- 两栏
        columns = QHBoxLayout()
        columns.setSpacing(16)

        self.font_list = QListWidget()
        self.font_list.setObjectName("FontList")
        self.font_list.setFixedWidth(240)
        self.font_list.setMinimumHeight(300)
        self.font_list.setUniformItemSizes(True)
        self.font_list.setWordWrap(False)
        self.font_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.font_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.font_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.font_list.currentItemChanged.connect(self._refresh)
        self.font_list.itemActivated.connect(self._on_activated)
        columns.addWidget(self.font_list)

        right = QVBoxLayout()
        right.setSpacing(10)

        # ---- 参数区：字号 / 字重 / 行距 / 斜体（2×2 网格，标签右对齐）
        #
        # 字号与行距都用**下拉框**而不是 QSpinBox：QSpinBox 右边那对上下
        # 微调按钮在 QSS 定制后要么没箭头（像坏了）、要么在窄框里挤成一团；
        # 而且这几个参数本来就是有限档位，选比拨更省事。
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.size_box = _value_combo(SIZE_CHOICES, int(size), " 号")
        self.size_box.currentIndexChanged.connect(self._refresh)

        self.weight_box = CompactComboBox(rows=3)
        for text, w in WEIGHTS:
            self.weight_box.addItem(text, w)
        self.weight_box.setFixedWidth(FIELD_WIDTH)
        self._set_weight(weight)
        self.weight_box.currentIndexChanged.connect(self._refresh)

        self.line_box = _value_combo(LINE_CHOICES, int(line_percent), " %")
        self.line_box.currentIndexChanged.connect(self._refresh)

        self.italic_box = QCheckBox("斜体")
        self.italic_box.setChecked(bool(italic))
        self.italic_box.toggled.connect(self._refresh)

        grid.addWidget(self._label("字号"), 0, 0)
        grid.addWidget(self.size_box, 0, 1)
        grid.addWidget(self._label("字重"), 0, 2)
        grid.addWidget(self.weight_box, 0, 3)
        grid.addWidget(self._label("行距"), 1, 0)
        grid.addWidget(self.line_box, 1, 1)
        grid.addWidget(self.italic_box, 1, 2, 1, 2, Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(4, 1)
        right.addLayout(grid)

        right.addWidget(self._label("预览"))
        card = QFrame()
        card.setObjectName("PreviewCard")
        card.setStyleSheet(
            f"#PreviewCard {{ background: {Color.card}; border: 1px solid {Color.border};"
            f"border-radius: 8px; }}")
        card.setMinimumHeight(120)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(16, 12, 16, 12)
        self.preview = QLabel(SAMPLE)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setWordWrap(True)
        inner.addWidget(self.preview)
        right.addWidget(card, 1)

        self.summary = QLabel()
        self.summary.setStyleSheet(f"color: {Color.text_tertiary}; font-size: 11px;")
        right.addWidget(self.summary)
        columns.addLayout(right, 1)

        self.root.addLayout(columns, 1)

        # 先灌数据、再恢复「上次的选择」：列表要有一条与当前配置同名的项
        self._populate(family)

        # ---------------------------------------------------------- 底部
        footer = QHBoxLayout()
        reset = QPushButton("恢复默认值")
        reset.setToolTip(f"回到 {DEFAULT_FONT_FAMILY} {DEFAULT_FONT_SIZE} 号")
        reset.clicked.connect(self._restore_default)
        footer.addWidget(reset)
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.ok = PrimaryButton("确定")
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.accept)
        footer.addWidget(self.ok)
        self.root.addLayout(footer)

        self._refresh()

    # ------------------------------------------------------------ 构 造
    def _populate(self, family: str) -> None:
        """把系统字体灌进列表（每条用自身字体渲染族名），并选中 ``family``。"""
        families = list(QFontDatabase.families())
        # 配置里的字体可能已卸载：仍然补一条进去，否则「确定」会把族名改掉
        if family and family not in families:
            families.insert(0, family)
        if not families:                       # 离屏 / 字体库为空：至少保住当前值
            families = [family or DEFAULT_FONT_FAMILY]

        for name in families:
            item = QListWidgetItem(name)
            # FontRole 让每条用自己的字体画 —— 选之前就能看出字形差异
            item.setData(Qt.ItemDataRole.FontRole, QFont(name, LIST_POINT_SIZE))
            item.setToolTip(name)
            self.font_list.addItem(item)

        self._select(family or DEFAULT_FONT_FAMILY)
        if self.font_list.currentItem() is not None:
            self.font_list.setFocus()

    def _select(self, family: str) -> bool:
        """在列表里选中 ``family``（找不到时不改选择，返回 False）。"""
        for i in range(self.font_list.count()):
            item = self.font_list.item(i)
            if item.text() == family:
                self.font_list.setCurrentItem(item)
                self.font_list.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                return True
        return False

    # ------------------------------------------------------------ 行 为
    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        first_visible: QListWidgetItem | None = None
        for i in range(self.font_list.count()):
            item = self.font_list.item(i)
            hit = not needle or needle in item.text().lower()
            item.setHidden(not hit)
            if hit and first_visible is None:
                first_visible = item
        # 当前项被过滤掉时，把选择落到第一条可见项上，预览才不会停在看不见的字体
        current = self.font_list.currentItem()
        if first_visible is not None and (current is None or current.isHidden()):
            self.font_list.setCurrentItem(first_visible)

    def _on_activated(self, _item: QListWidgetItem) -> None:
        self.accept()

    def _current_family(self) -> str:
        item = self.font_list.currentItem()
        if item is not None and not item.isHidden():
            return item.text()
        return self._fallback_family

    def _restore_default(self) -> None:
        self.search.clear()
        if not self._select(DEFAULT_FONT_FAMILY):
            self._fallback_family = DEFAULT_FONT_FAMILY
        self._select_value(self.size_box, DEFAULT_FONT_SIZE, " 号")
        self._set_weight(Settings.font_weight)
        self.italic_box.setChecked(Settings.font_italic)
        self._select_value(self.line_box, Settings.line_height_percent, " %")
        self._refresh()

    @staticmethod
    def _select_value(box: CompactComboBox, value: int, suffix: str) -> None:
        """在下拉框里选中 ``value``；档位里没有就按数值顺序补一条。"""
        idx = box.findData(int(value))
        if idx < 0:
            values = [box.itemData(i) for i in range(box.count())]
            idx = sum(1 for v in values if v < int(value))
            box.insertItem(idx, f"{int(value)}{suffix}", int(value))
        box.setCurrentIndex(idx)

    def _set_weight(self, weight: int) -> None:
        """把字重设为最接近的档位（配置里出现 550 之类的散值时取近似档）。"""
        idx = min(range(len(WEIGHTS)), key=lambda i: abs(WEIGHTS[i][1] - int(weight)))
        self.weight_box.setCurrentIndex(idx)

    def _refresh(self, *_args) -> None:
        family = self._current_family()
        size = int(self.size_box.currentData())
        weight = int(self.weight_box.currentData())
        italic = self.italic_box.isChecked()
        # 预览必须走**样式表**：主题里那条 ``* {{ font-family: ... }}`` 会盖掉
        # setFont（QSS 优先级高于 setFont，编辑器换字体也踩过同一个坑）——
        # 之前用 setFont 设预览，结果不管选哪个字体，样张永远是全局雅黑
        # （用户报「字体选择实际展示没有任何变化」就是这个）。
        self.preview.setStyleSheet(
            f'font-family: "{family}"; font-size: {size}pt;'
            f'font-weight: {weight};'
            f'font-style: {"italic" if italic else "normal"};'
            f'color: {Color.text};')
        line = int(self.line_box.currentData())
        self.summary.setText(f"{family} · {size} 号 · 行距 {line}%")

    # ------------------------------------------------------------ 取 值
    def selected(self) -> tuple[str, int, int, bool, int]:
        """确定后取值：(字体族, 字号, 字重, 斜体, 行距%)。

        族名取列表项的文字（``currentText`` 语义），不是 ``QFont.family()``：
        后者是 **Qt 解析后**的族名（字体没装时会被替换成 ``Sans Serif`` 之类的
        兜底族），存进配置就会把用户选的族名丢掉。
        """
        return (self._current_family(), int(self.size_box.currentData()),
                int(self.weight_box.currentData()), self.italic_box.isChecked(),
                int(self.line_box.currentData()))

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFixedWidth(40)
        label.setStyleSheet(f"color: {Color.text_secondary}; font-size: 12px;")
        # QLabel 竖直默认 Preferred 会被 QVBoxLayout 拉高（右栏 SectionLabel 同款坑）
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        return label


__all__ = ["FontDialog", "DEFAULT_FONT_FAMILY", "DEFAULT_FONT_SIZE", "SAMPLE",
           "LIST_POINT_SIZE", "WEIGHTS"]
