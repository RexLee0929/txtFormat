"""Fluent 风格的自定义控件。"""

from __future__ import annotations

from PySide6.QtCore import (Property, QEasingCurve, QEvent, QPointF, QPropertyAnimation,
                            QRect, QRectF, QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from . import icons
from .theme import ACCENT, Color


class Card(QFrame):
    """Win11 卡片容器：白底、1px 边框、8px 圆角。"""

    def __init__(self, parent: QWidget | None = None, padding: int = 12, spacing: int = 8):
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(padding, padding, padding, padding)
        self._layout.setSpacing(spacing)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget


class SectionLabel(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setProperty("role", "title")
        font = self.font()
        font.setPointSizeF(10.5)
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)


class Caption(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setProperty("role", "caption")
        self.setWordWrap(True)


class CommandButton(QPushButton):
    """命令栏按钮：图标 + 文字，悬停时浅色背景。"""

    def __init__(self, text: str, icon_name: str = "", parent: QWidget | None = None,
                 kind: str = "subtle", icon_color: str | None = None):
        super().__init__(text, parent)
        self.setProperty("kind", kind)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_name:
            self.setIcon(icons.icon(icon_name, icon_color or Color.text, 18))
            self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)


class PrimaryButton(QPushButton):
    def __init__(self, text: str, icon_name: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setProperty("kind", "primary")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_name:
            self.setIcon(icons.icon(icon_name, "#FFFFFF", 18))
            self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(32)
        self.setMinimumWidth(88)


class IconButton(QPushButton):
    def __init__(self, icon_name: str, tooltip: str = "", parent: QWidget | None = None,
                 size: int = 32, color: str = Color.text):
        super().__init__(parent)
        self.setProperty("kind", "subtle")
        self.setIcon(icons.icon(icon_name, color, 18))
        self.setIconSize(QSize(18, 18))
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class ToggleSwitch(QWidget):
    """Win11 开关：轨道 + 滑块，带过渡动画。"""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent: QWidget | None = None,
                 width: int = 40, height: int = 20):
        super().__init__(parent)
        self._checked = checked
        self._pos = 1.0 if checked else 0.0
        self._w = width
        self._h = height
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ---- knob 属性（0..1）
    def get_knob(self) -> float:
        return self._pos

    def set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, get_knob, set_knob)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, value: bool, emit: bool = False) -> None:
        if value == self._checked:
            return
        self._checked = value
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if value else 0.0)
        self._anim.start()
        if emit:
            self.toggled.emit(value)

    def mouseReleaseEvent(self, event):        # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.setChecked(not self._checked, emit=True)
        super().mouseReleaseEvent(event)

    def sizeHint(self) -> QSize:               # noqa: N802
        return QSize(self._w, self._h)

    def paintEvent(self, event):               # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = self._h / 2
        track = QRectF(0, 0, self._w, self._h)
        off_color = QColor("#8C8C8C")
        on_color = QColor(ACCENT)
        color = QColor(
            round(off_color.red() + (on_color.red() - off_color.red()) * self._pos),
            round(off_color.green() + (on_color.green() - off_color.green()) * self._pos),
            round(off_color.blue() + (on_color.blue() - off_color.blue()) * self._pos),
        )
        if not self.isEnabled():
            color = QColor(Color.disabled)
        painter.setPen(Qt.PenStyle.NoPen)
        if self._pos < 0.5:
            painter.setBrush(QColor("#FFFFFF"))
            painter.setPen(QPen(QColor(Color.border_strong), 1))
            painter.drawRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#5C5C5C"))
            d = self._h - 8
            x = 4 + self._pos * (self._w - self._h)
            painter.drawEllipse(QRectF(x, (self._h - d) / 2, d, d))
        else:
            painter.setBrush(color)
            painter.drawRoundedRect(track, radius, radius)
            d = self._h - 8
            x = 4 + self._pos * (self._w - self._h)
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawEllipse(QRectF(x, (self._h - d) / 2, d, d))
        painter.end()


class SearchBox(QLineEdit):
    def __init__(self, placeholder: str = "搜索", parent: QWidget | None = None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.addAction(icons.icon("search", Color.text_secondary, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.setMinimumHeight(32)


class CompactComboBox(QComboBox):
    """下拉框：限制弹出列表的行数，并清理 Qt 弹层的接缝与滚动三角。

    Qt 在弹出列表比内容矮时，会在弹层容器（QComboBoxPrivateContainer）里插一条
    ``QComboBoxPrivateScroller`` 横带做"下面还有更多"的提示。样式表一介入，这条横带
    就渲染成一道多余的白边 + 右下小三角，看起来就是"错乱/错层"。

    两条硬规矩（都是踩过坑的）：

    * **只隐藏、不删除 scroller**：容器持有它的指针，``setParent(None)`` +
      ``deleteLater()`` 会留下悬空指针，下次 ``showPopup`` 直接 access violation 崩溃。
    * **高度必须在弹出之前定好**：``showPopup`` 之后再 ``resize`` 弹层，Qt 的
      上下翻转判断已经算过一轮了，于是同一个下拉每次展开的位置都不一样
      （实测正则库在 y=0 与 y=547 之间乱跳）。所以改成先 ``setFixedHeight``
      再 ``super().showPopup()``，让 Qt 一开始就按正确尺寸定位。
    """

    def __init__(self, rows: int = 10, parent: QWidget | None = None):
        super().__init__(parent)
        self._rows = rows
        self.setMaxVisibleItems(rows)
        self._popup = None
        self._hooked = False
        self._tidying = False

    def _row_height(self) -> int:
        return max(self.view().sizeHintForRow(0), 22)

    def _body_height(self) -> int:
        rows = max(1, min(self.count(), self._rows))
        return self._row_height() * rows

    def _hide_scroller(self) -> None:
        """把 Qt 插的滚动提示横带藏起来（只隐藏，不销毁）。"""
        popup = self._popup
        if popup is None:
            return
        for child in popup.children():
            if (isinstance(child, QWidget)
                    and "Scroller" in child.metaObject().className()):
                child.hide()
                child.setMaximumHeight(0)

    def showPopup(self) -> None:               # noqa: N802 - Qt 命名
        # 先定高，再弹出 —— 顺序反了位置就会飘。
        if self.count():
            self.view().setFixedHeight(self._body_height())
        super().showPopup()

        self._popup = self.view().window()
        if not self._hooked and self._popup is not None:
            self._popup.installEventFilter(self)
            self._hooked = True
        # 弹出后 Qt 可能又把 scroller 显示回来，收一次尾（不动尺寸）。
        QTimer.singleShot(0, self._tidy)

    def _tidy(self) -> None:
        """藏掉 scroller 并把布局边距归零。不碰弹层尺寸，避免位置漂移。"""
        if self._tidying or self._popup is None:
            return
        self._tidying = True
        try:
            self._hide_scroller()
            lay = self._popup.layout()
            if lay is not None:
                lay.setContentsMargins(0, 0, 0, 0)
                lay.setSpacing(0)
        finally:
            self._tidying = False

    def eventFilter(self, obj, event):         # noqa: N802 - Qt 命名
        if obj is self._popup and event.type() in (
                QEvent.Type.Show, QEvent.Type.Resize, QEvent.Type.Paint):
            self._tidy()
        return super().eventFilter(obj, event)


class StatPill(QWidget):
    """状态胶囊：小圆点 + 文本。"""

    def __init__(self, text: str = "", color: str = Color.text_secondary, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = QColor(color)
        self._text = text
        self._font = QFont(self.font())
        self._font.setPointSizeF(9)
        self.setFixedHeight(18)

    def setText(self, text: str) -> None:      # noqa: N802
        self._text = text
        self.updateGeometry()
        self.update()

    def setColor(self, color: str) -> None:    # noqa: N802
        self._color = QColor(color)
        self.update()

    def sizeHint(self) -> QSize:               # noqa: N802
        metrics = self.fontMetrics()
        return QSize(10 + metrics.horizontalAdvance(self._text) + 4, 18)

    def paintEvent(self, event):               # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(QPointF(4, 9), 3, 3)
        painter.setPen(QPen(QColor(Color.text_secondary)))
        painter.setFont(self._font)
        painter.drawText(QRectF(12, 0, self.width() - 12, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)
        painter.end()


class Toast(QLabel):
    """底部浮动提示（3 秒后淡出）。"""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(
            f"background: {Color.text}; color: #FFFFFF; border-radius: 8px;"
            f"padding: 10px 18px; font-size: 12px;"
        )
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(180)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text: str, msec: int = 2600) -> None:
        self.setText(text)
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(msec)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()
        self._anim.finished.connect(self._maybe_hide)

    def _maybe_hide(self) -> None:
        try:
            self._anim.finished.disconnect(self._maybe_hide)
        except (RuntimeError, TypeError):
            pass
        if self._effect.opacity() < 0.05:
            self.hide()

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        width = min(max(self.sizeHint().width() + 24, 200), parent.width() - 80)
        height = max(self.heightForWidth(width), 36)
        self.setFixedWidth(width)
        self.setFixedHeight(height)
        self.move((parent.width() - width) // 2, parent.height() - height - 56)


class CopyChip(QFrame):
    """联系方式胶囊：看起来是普通文字，点击即复制，不打开任何外部程序。"""

    copied = Signal(str)

    def __init__(self, text: str, value: str = "", icon_name: str = "mail",
                 hint: str = "点击复制", parent: QWidget | None = None):
        super().__init__(parent)
        self._text = text
        self._value = value or text
        self._hint = hint
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{self._value}\n{hint}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 3, 11, 3)
        layout.setSpacing(6)
        self._icon = QLabel()
        self._icon.setPixmap(icons.pixmap(icon_name, Color.text_secondary, 14))
        self._icon.setFixedSize(14, 14)
        layout.addWidget(self._icon)
        self._label = QLabel(text)
        self._label.setStyleSheet(f"color: {Color.text}; font-size: 12px;")
        layout.addWidget(self._label)
        self._apply_style()

    def _apply_style(self, active: bool = False) -> None:
        border = ACCENT if active else Color.border
        bg = QColor(ACCENT).lighter(188).name() if active else Color.card
        self.setStyleSheet(
            f"CopyChip {{ background: {bg}; border: 1px solid {border};"
            f"border-radius: 12px; }}")

    def mouseReleaseEvent(self, event):        # noqa: N802 - Qt 命名
        if event.button() == Qt.MouseButton.LeftButton:
            self.copy()
        super().mouseReleaseEvent(event)

    def copy(self) -> None:
        """复制到剪贴板；文字与尺寸保持不变，只闪一下边框。"""
        QApplication.clipboard().setText(self._value)
        self._apply_style(True)
        QTimer.singleShot(900, lambda: self._apply_style(False))
        self.copied.emit(self._value)


class Divider(QFrame):
    def __init__(self, horizontal: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        if horizontal:
            self.setFixedHeight(1)
            self.setStyleSheet(f"background: {Color.border};")
        else:
            self.setFixedWidth(1)
            self.setStyleSheet(f"background: {Color.border};")


def hbox(*widgets: QWidget, spacing: int = 8, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QWidget:
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for w in widgets:
        lay.addWidget(w)
    return box


__all__ = ["Card", "SectionLabel", "Caption", "CommandButton", "PrimaryButton",
           "IconButton", "ToggleSwitch", "SearchBox", "StatPill", "Toast",
           "Divider", "hbox"]
