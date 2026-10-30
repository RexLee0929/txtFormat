"""文本编辑区：行号、当前行高亮、水线、查找高亮、自动卷屏。"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QFontMetricsF, QPainter, QTextCursor,
                           QTextFormat)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from .theme import ACCENT, Color


class LineNumberArea(QWidget):
    def __init__(self, editor: "TextEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:              # noqa: N802
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event):              # noqa: N802
        self._editor.paint_line_numbers(event)


class TextEditor(QPlainTextEdit):
    stats_changed = Signal()
    font_changed = Signal(str, float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("role", "editor")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        self.setTabChangesFocus(False)
        self.setUndoRedoEnabled(True)
        self.setCursorWidth(2)

        self._line_area = LineNumberArea(self)
        self._guide_column = 0
        self._highlights: list[QTextEdit.ExtraSelection] = []
        self._auto_scroll = False
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(40)
        self._scroll_timer.timeout.connect(self._do_auto_scroll)
        self._reading_mode = False

        self.blockCountChanged.connect(self._update_area_width)
        self.updateRequest.connect(self._on_update_request)
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        self.selectionChanged.connect(self.stats_changed.emit)

        self._update_area_width()
        self._refresh_extra_selections()

    # ------------------------------------------------------------ 行号
    def line_number_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _margins(self) -> tuple[int, int, int, int]:
        """普通模式留出行号宽度；阅读模式改成居中的窄栏。"""
        if self._reading_mode:
            column = 720                                   # 阅读栏宽度（逻辑像素）
            side = max(28, (self.width() - column) // 2)
            return (side, 20, side, 20)
        return (self.line_number_width(), 0, 0, 0)

    def _update_area_width(self) -> None:
        left, top, right, bottom = self._margins()
        self.setViewportMargins(left, top, right, bottom)

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_area_width()

    def resizeEvent(self, event):             # noqa: N802
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_width(), cr.height()))
        if self._reading_mode:
            self._update_area_width()

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor(Color.card_alt))
        painter.setPen(QColor("#C6C6C6"))
        painter.drawLine(self._line_area.width() - 1, event.rect().top(),
                         self._line_area.width() - 1, event.rect().bottom())

        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().blockNumber()
        metrics = self.fontMetrics()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor(ACCENT if number == current else "#9A9A9A"))
                painter.drawText(0, top, self._line_area.width() - 8,
                                 metrics.height(), Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1

    # ------------------------------------------------------------ 外观
    def _apply_font(self, family: str, size_pt: float) -> None:
        """固定字号到 0.5pt 台阶；实际绘制字号由主窗口用 QSS 同步（QSS 优先级高于 setFont）。"""
        size = round(float(size_pt) * 2) / 2
        font = QFont(family)
        font.setPointSizeF(size)
        font.setStyleStrategy(QFont.StyleStrategy.PreferDefault)   # 交给系统做 ClearType
        self.setFont(font)
        self.setTabStopDistance(QFontMetricsF(font).horizontalAdvance("　") * 2)
        self._font_family = family
        self._font_size = size
        self.font_changed.emit(family, size)

    def set_editor_font(self, family: str, size_pt: float, line_percent: int = 160) -> None:
        self._line_percent = line_percent
        self._apply_font(family, size_pt)
        self.document().setDocumentMargin(6)
        self._update_area_width()
        self.stats_changed.emit()

    def set_guide_column(self, column: int) -> None:
        self._guide_column = max(0, column)
        self.viewport().update()

    def set_auto_scroll(self, enabled: bool) -> None:
        self._auto_scroll = enabled
        if enabled:
            self._scroll_timer.start()
        else:
            self._scroll_timer.stop()

    def _do_auto_scroll(self) -> None:
        bar = self.verticalScrollBar()
        if bar.value() >= bar.maximum():
            bar.setValue(0)
        else:
            bar.setValue(bar.value() + bar.singleStep() * 2)

    def set_reading_mode(self, enabled: bool) -> None:
        self._reading_mode = enabled
        self.setReadOnly(enabled)
        self.setCursorWidth(0 if enabled else 2)
        self._line_area.setVisible(not enabled)
        self._update_area_width()
        self._refresh_extra_selections()
        self.viewport().update()

    @property
    def reading_mode(self) -> bool:
        return self._reading_mode

    # ------------------------------------------------------------ 高亮
    def _refresh_extra_selections(self) -> None:
        selections: list[QTextEdit.ExtraSelection] = []
        cursor = self.textCursor()
        if not self._reading_mode and cursor.hasSelection() is False:
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor("#F7FAFD"))
            sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            sel.cursor = cursor
            sel.cursor.clearSelection()
            selections.append(sel)
        selections.extend(self._highlights)
        self.setExtraSelections(selections)

    def _on_cursor_moved(self) -> None:
        self._refresh_extra_selections()
        self.stats_changed.emit()

    def highlight_matches(self, spans: list[tuple[int, int]], current: int = -1) -> None:
        highlights: list[QTextEdit.ExtraSelection] = []
        for idx, (start, end) in enumerate(spans[:4000]):
            sel = QTextEdit.ExtraSelection()
            color = QColor("#FFE58F") if idx != current else QColor("#FFB86B")
            sel.format.setBackground(color)
            cursor = QTextCursor(self.document())
            cursor.setPosition(max(0, start))
            cursor.setPosition(max(0, end), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cursor
            highlights.append(sel)
        self._highlights = highlights
        self._refresh_extra_selections()

    def clear_highlights(self) -> None:
        self._highlights = []
        self._refresh_extra_selections()

    # ------------------------------------------------------------ 水线
    def paintEvent(self, event):               # noqa: N802
        super().paintEvent(event)
        if self._guide_column > 0:
            painter = QPainter(self.viewport())
            metrics = QFontMetrics(self.font())
            x = self.viewportMargins().left() + metrics.horizontalAdvance("　") * self._guide_column
            if 0 < x < self.viewport().width():
                pen = painter.pen()
                pen.setColor(QColor("#E3E3E3"))
                pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(x, 0, x, self.viewport().height())
            painter.end()

    # ------------------------------------------------------------ 统计
    def selection_stats(self) -> tuple[int, int, int]:
        cursor = self.textCursor()
        selected = len(cursor.selectedText())
        text = self.toPlainText()
        return len(text), text.count("\n") + 1 if text else 0, selected

    def go_to_line(self, line: int) -> None:
        block = self.document().findBlockByLineNumber(max(0, line - 1))
        if block.isValid():
            cursor = QTextCursor(block)
            self.setTextCursor(cursor)
            self.centerCursor()

    def go_to_percent(self, percent: int) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(int(bar.maximum() * max(0, min(100, percent)) / 100))

    def zoom_by(self, delta: float) -> None:
        size = max(7.0, min(36.0, getattr(self, "_font_size", 11.0) + delta))
        self._apply_font(getattr(self, "_font_family", "Microsoft YaHei UI"), size)
        self._update_area_width()


__all__ = ["TextEditor", "LineNumberArea"]
