"""自绘错误框（规范 §七.4）。

规范对「未捕获异常」的规定是**三通道**：写 ``error.log`` + 状态栏红字 + 自绘错误框。
本文件负责第三通道，并且必须满足 §七.2 的对话框规格：

* 标题栏走与主窗口同一套 DWM 定制（继承 :class:`BaseDialog`）；
* **窗口标题只写程序名** —— 事情本身写进卡片内标题；
* **不可拉伸**：宽度固定、高度按内容拟合；
* 按钮最多两个，主按钮动词短语、次按钮「关闭」等价取消；
* 整条路径不发声、不叠弹（同屏只允许一个，后来的只进日志）。

排版要点（三轮返工后定稿，问题都出在「左缘」和「高度」上）：

* **图标在标题行的左侧**（``error`` 24px、与标题同一个语义色 ``Color.danger``，
  《图标规范》§七「对话框 Danger / 错误框」）。正文列整体缩进到标题文字下方，
  于是整块只有**两条左缘**：图标列 + 文字列。曾经把图标孤悬在标题上方、
  套一个白卡片把文字推到第三列，结果三条竖线互相打架；
* **不套卡片**：卡片会多出「边框 20 / 卡内文字 34 / 标题 54」三条线；
* 层次靠字号与灰阶：标题 14px 半粗 → 主因 12px 正文 → 下一步 12px 灰 → 日志 11px 浅灰；
* 底部只放按钮，日志状态收在文字列最后一行；「关闭」是主按钮（强调色实心），
  「打开日志」是次按钮 —— 原来两个都是白底描边，主次不分。

图标与标题**同源同色**是硬要求（§四.1）：文字用 ``Color.danger``，图标也必须用它，
另挑一个红会有肉眼可见的色差，看着像两套主题。
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..core.version import APP_NAME
from . import icons
from .dialogs import BaseDialog
from .theme import Color
from .widgets import PrimaryButton

#: 图标尺寸与列宽（《图标规范》§三.4：错误框 24）。正文列缩进 = 24 + 12。
ICON_SIZE = 24
ICON_GAP = 12
ICON_COL = ICON_SIZE + ICON_GAP

#: 同屏只允许一个错误框（规范 §七.1「弹窗叠弹窗」禁令）
_showing: list["ErrorDialog"] = []

class ErrorDialog(BaseDialog):
    """错误框：说清「发生了什么 + 下一步」，技术细节留给 error.log。"""

    def __init__(self, message: str, log_path: str = "", parent: QWidget | None = None):
        super().__init__(APP_NAME, parent)            # 窗口标题只写程序名

        has_log = bool(log_path) and os.path.exists(log_path)

        # ---- 两列：图标 | 文字（标题 / 主因 / 下一步 / 日志去向）
        #
        # 图标只在标题行占位，正文列整体缩进到标题文字下方 —— 两条左缘，
        # 读者的视线沿「图标 → 标题 → 正文」一条竖线往下走。
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(6)

        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.setSpacing(ICON_GAP)
        mark = QLabel()
        mark.setPixmap(icons.pixmap("error", Color.danger, ICON_SIZE))
        mark.setFixedSize(ICON_SIZE, ICON_SIZE)
        mark.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        head_row.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)

        head = QLabel("刚才的操作没有完成")
        head.setStyleSheet(f"color: {Color.text}; font-size: 14px; font-weight: 600;")
        # QLabel 默认竖直 Preferred，会被 QBoxLayout 拉高（实测标题行 44px，
        # 标题和下方文字之间凭空多出一条空带）—— 与右栏 SectionLabel 同一坑。
        head.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        head_row.addWidget(head, 0, Qt.AlignmentFlag.AlignVCenter)
        head_row.addStretch(1)
        text_col.addLayout(head_row)
        text_col.addSpacing(10)     # 标题与主因之间拉开一档，标题才会独立成块

        detail = message.strip() or "程序内部出现了未处理的异常。"
        if len(detail) > 300:
            detail = detail[:300] + "…"
        body = QLabel(detail)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(f"color: {Color.text}; font-size: 12px;")
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        body.setContentsMargins(ICON_COL, 0, 0, 0)     # 与标题文字左对齐
        text_col.addWidget(body)

        next_step = QLabel("可以打开日志看详情；关掉这个框就能继续用。"
                           if has_log else "关掉这个框就能继续用。")
        next_step.setWordWrap(True)
        next_step.setStyleSheet(f"color: {Color.text_secondary}; font-size: 12px;")
        next_step.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        next_step.setContentsMargins(ICON_COL, 0, 0, 0)
        text_col.addWidget(next_step)

        if has_log:
            note = QLabel("详情已写入 error.log")
            note.setStyleSheet(f"color: {Color.text_tertiary}; font-size: 11px;")
            note.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            note.setContentsMargins(ICON_COL, 0, 0, 0)
            text_col.addWidget(note)

        self.root.addLayout(text_col)

        # ---- 按钮栏：底部只放按钮
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch(1)
        self.log_btn: QPushButton | None = None
        if has_log:
            self.log_btn = QPushButton("打开日志")
            self.log_btn.clicked.connect(self._open_log)
            footer.addWidget(self.log_btn)
        close = PrimaryButton("关闭")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        self.root.addLayout(footer)

        self._log_path = log_path

    # 尺寸完全交给 BaseDialog.fit_content()：先按内容定宽、再按该宽度算高
    # （带 wordWrap 的 QLabel 高度依赖宽度，顺序反了会多出一条空带）。
    # 这里曾经写死 WIDTH=480 并自己覆写 showEvent —— 那正是 §十.4 点名的
    # 「每个框都往构造参数里传一个死数」，已删除。

    def natural_width(self) -> int:
        """在基类的「最长一行」之外补上图标列。

        正文列整体缩进了 :data:`ICON_COL`，而基类只加了对话框内边距（40），
        不补这 36px 的话长文案会平白多折一行、图标也会贴到文字上（§十.4 的
        「宽度跟着内容走」照样成立：文案变长，宽度还是跟着变）。
        """
        return super().natural_width() + ICON_COL

    def _open_log(self) -> None:
        try:
            os.startfile(self._log_path)                # noqa: S606
        except Exception:      # noqa: BLE001 - 打不开日志不影响关闭
            pass
        self.accept()


def show_error(message: str, log_path: str = "", parent: QWidget | None = None) -> None:
    """唯一入口：开一个错误框（同屏只允许一个，后来的直接丢弃）。"""
    if _showing:
        return
    dlg = ErrorDialog(message, log_path, parent)
    _showing.append(dlg)
    try:
        dlg.exec()
    finally:
        _showing.remove(dlg)


__all__ = ["ErrorDialog", "show_error"]
