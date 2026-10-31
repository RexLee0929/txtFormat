"""Fluent 风格的自定义控件。"""

from __future__ import annotations

import sys

from PySide6.QtCore import (QEvent, QPoint, QPropertyAnimation, QRect, QRectF,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import (QColor, QFont, QKeySequence, QPainter, QPainterPath,
                           QPen, QRegion)
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

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
        # 用像素字号（与 QSS `font-size:19px` 一致），不用 pointSize：
        # QLabel.sizeHint 按控件字体算，QSS 却按自己的字体渲染 —— 两边不一致时
        # 要么裁字、要么 sizeHint 虚高。
        font.setPixelSize(19)
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)
        # 关键：竖直 Fixed。QLabel 默认 Preferred，可被 QBoxLayout 拉高 ——
        # 当面板里其他控件（如固定行高的正则列表）吃不完剩余空间时，
        # 多出来的几十像素全被塞进标题，文字垂直居中后上下各空一条带，
        # 看起来就是「标题和下面的框间隔太大」（实测标题被拉到 76px 高）。
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)


class Caption(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setProperty("role", "caption")
        self.setWordWrap(True)


class CommandButton(QPushButton):
    """命令栏按钮：图标 + 文字，悬停时浅色背景。

    按钮只负责**量出自己两端宽度**（完整文字 / 只留图标），收不收文字由命令栏
    统一决定（见 ``MainWindow._fit_command_bar``）。

    为什么不在按钮里自己判断：QBoxLayout 遇到放不下时只会把各项**按比例压扁**，
    文字就被裁成「一键审」这种半截字，它没有"按重要性依次收起"的原生机制
    （那是 QToolBar 内部实现 + 溢出菜单；而溢出菜单是原生 QMenu，会把已经修掉的
    弹层圆角黑边问题带回来）。所以收起顺序只能由容器算 —— 但状态完全由当前
    宽度推导、每次 resize 重算，不存在"已收起集合"那种卡住不恢复的中间态。
    """

    def __init__(self, text: str, icon_name: str = "", parent: QWidget | None = None,
                 kind: str = "subtle", icon_color: str | None = None,
                 collapse_when_tight: bool = False):
        super().__init__(text, parent)
        self.setProperty("kind", kind)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_name:
            self.setIcon(icons.icon(icon_name, icon_color or Color.text, 18))
            self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._full_text = text
        self.collapse_when_tight = collapse_when_tight
        self._full_w = 0          # 完整文字的自然宽度（量一次存起来）
        self._compact_w = 0       # 只留图标的自然宽度
        self._measuring = False

    # ---------------------------------------------------------- 两种宽度
    def _measure(self) -> None:
        """量出两种自然宽度：完整文字 / 只留图标。

        必须让按钮自己算（``super().sizeHint()``），而不是拿
        ``QStyle.sizeFromContents`` 改 ``opt.text`` 去估 —— 后者在带样式表的
        按钮上会返回 -1（实测），布局会把按钮压成 0 宽。
        """
        if self._measuring:
            return
        self._measuring = True
        try:
            self.ensurePolished()
            self._full_w = super().sizeHint().width()
            keep = self.text()
            if keep:
                self.setText("")
                self._compact_w = max(24, super().sizeHint().width())
                self.setText(keep)
            else:
                self._compact_w = self._full_w
        finally:
            self._measuring = False

    def natural_width(self) -> int:
        """显示完整文字时需要的宽度。"""
        if not self._full_w:
            self._measure()
        return self._full_w or super().sizeHint().width()

    def compact_width(self) -> int:
        """只显示图标时需要的宽度。"""
        if not self._full_w:
            self._measure()
        return self._compact_w or self.natural_width()

    def showEvent(self, event) -> None:       # noqa: N802 - Qt 命名
        super().showEvent(event)
        if not self._full_w:
            self._measure()

    def changeEvent(self, event) -> None:     # noqa: N802 - Qt 命名
        super().changeEvent(event)
        # 字体/样式变了，量出来的宽度作废，下次布局时重量
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._full_w = self._compact_w = 0

    def sizeHint(self) -> QSize:              # noqa: N802 - Qt 命名
        if not self._full_w:
            return super().sizeHint()
        # 始终报完整文字宽度：与当前是否收起无关（宽度由命令栏 setFixedWidth 钉住）
        return QSize(self._full_w, super().sizeHint().height())

    def set_label_visible(self, visible: bool) -> None:
        """收起/展开按钮文字。收起后只留图标，tooltip 不变。"""
        want = self._full_text if visible else ""
        if self.text() != want:
            self.setText(want)

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


class SearchBox(QLineEdit):
    def __init__(self, placeholder: str = "搜索", parent: QWidget | None = None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.addAction(icons.icon("search", Color.text_secondary, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.setMinimumHeight(32)


class CompactComboBox(QComboBox):
    """下拉框：限制弹层行数，宽度与当前选中项解耦，位置钉死在下拉框下方。

    这里原先有约 175 行手写逻辑：事件过滤器在 Move/Resize/Paint/Expose 上反复
    纠正弹层、自己隐藏 Qt 插入的 ``QComboBoxPrivateScroller`` 横带、还要算翻转
    与越界。其实大部分都能交回 Qt：

    * **宽度跟着当前项变**（选中更长的项，宽度一变，左右对齐方式跟着切换 →
      整个框看着跳位）：弹出前把视图最小宽度设成"最长项"的宽度即可，
      与当前选中项无关。
    * **右下角多出白横带 + 小三角**：那是 ``maxVisibleItems`` 触发滚动提示时
      Qt 插的 scroller；``setMaxVisibleItems(rows)`` 让它一次显示够行数，
      行数不超上限时压根不出现滚动条。

    只剩**位置**没法交给 Qt：列表需要滚动时，Qt 会把弹层整体挪动好让"当前选中项"
    贴在下拉框旁边，于是选中的项不同弹层就跳一截。这里只保留一处最小修正 ——
    弹出后把弹层摆回"贴着下拉框下方（下方不够则上方）、不越出屏幕"，十几行。
    """

    def __init__(self, rows: int = 10, parent: QWidget | None = None):
        super().__init__(parent)
        self._rows = max(1, rows)
        self.setMaxVisibleItems(self._rows)
        # 宽度按内容算（不受"当前项 + 省略号"挤压）
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.view().setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _popup_width(self) -> int:
        """弹层宽度：所有项里最宽那条 + 左右内边距，与当前选中项无关。"""
        if not self.count():
            return self.width()
        view = self.view()
        widest = max(view.sizeHintForColumn(i) for i in range(self.count()))
        # QSS 里 item 左右各 10px 内边距 + 视图 4px 内边距 + 1px 边框
        return max(self.width(), widest + 30)

    def showPopup(self) -> None:               # noqa: N802 - Qt 命名
        # 宽度必须在弹出**之前**定：弹出后 Qt 已按旧尺寸算过摆放，再改尺寸
        # 会让同一次展开的位置与上一次不一致。
        self.view().setMinimumWidth(self._popup_width())
        super().showPopup()
        # 位置是唯一没法交给 Qt 的：列表需要滚动时，Qt 会把弹层整体挪动，
        # 让「当前选中项」正好贴在下拉框旁边 —— 于是选中的项不同，弹层就跳一截
        # （用户实测报过「选一项再展开，整个框位置变了」）。这里在弹出后把弹层
        # 摆回固定位置：只由下拉框自身位置决定，与选中项无关。
        self._place_popup()
        QTimer.singleShot(0, self._place_popup)     # Qt 有时在下一拍再摆一次

    def _place_popup(self) -> None:
        popup = self.view().window()
        if popup is None or not self.isVisible():
            return
        # 弹层是「圆角容器 + 方角列表」叠出来的：列表把容器的圆角盖住，
        # 四角与选中项通到边上就成了「双层框」。和 Menu 同一套釜底抽薪 ——
        # setMask 把窗口直接裁成圆角，方角像素根本不存在。
        path = QPainterPath()
        path.addRoundedRect(QRectF(popup.rect()), 8, 8)
        popup.setMask(QRegion(path.toFillPolygon().toPolygon()))
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        origin = self.mapToGlobal(QPoint(0, 0))
        w, h = popup.width(), popup.height()

        # 默认贴下方、左边缘对齐；上方更宽裕时翻上去
        below = avail.bottom() - (origin.y() + self.height())
        above = origin.y() - avail.top()
        if below < h and above > below:
            x = origin.x() + self.width() - w
            y = origin.y() - h
        else:
            x = origin.x()
            y = origin.y() + self.height()

        x = max(avail.left(), min(x, avail.right() + 1 - w))
        y = max(avail.top(), min(y, avail.bottom() + 1 - h))
        if popup.pos() != QPoint(int(x), int(y)):
            popup.move(int(x), int(y))


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

    def show_message(self, text: str, msec: int = 2600, kind: str = "info") -> None:
        """显示提示。

        ``kind="error"`` 用警示色底（规范 §七 ①：状态栏瞬时提示，
        出错时用视觉手段区分，不弹窗、不发声）。
        """
        bg = Color.danger if kind == "error" else Color.text
        self.setStyleSheet(
            f"background: {bg}; color: #FFFFFF; border-radius: 8px;"
            f"padding: 10px 18px; font-size: 12px;"
        )
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
    """联系方式胶囊：看起来是普通文字，点击即复制，不打开任何外部程序。

    交互对齐 ComicConverter 的「关于」对话框：点一下 → 复制到剪贴板 →
    胶囊变强调色 → 右侧提示文字变成「已复制到剪贴板」，1.6 秒后自动恢复。
    胶囊本身的文字与尺寸全程不变。
    """

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
        layout.addWidget(self._label)
        self._apply_style()

    def _apply_style(self, active: bool = False) -> None:
        border = ACCENT if active else Color.border
        bg = QColor(ACCENT).lighter(188).name() if active else Color.card
        self.setStyleSheet(
            f"CopyChip {{ background: {bg}; border: 1px solid {border};"
            f"border-radius: 12px; }}")
        # 激活时文字也变强调色（ComicConverter 同款：只变色，不改文案）
        color = ACCENT if active else Color.text
        self._label.setStyleSheet(f"color: {color}; font-size: 12px;")

    def mouseReleaseEvent(self, event):        # noqa: N802 - Qt 命名
        if event.button() == Qt.MouseButton.LeftButton:
            self.copy()
        super().mouseReleaseEvent(event)

    def copy(self) -> bool:
        """复制到剪贴板。返回是否成功，供调用方决定提示文案。"""
        ok = True
        try:
            QApplication.clipboard().setText(self._value)
            ok = QApplication.clipboard().text() == self._value
        except Exception:
            ok = False
        self._apply_style(ok)
        QTimer.singleShot(1600, lambda: self._apply_style(False))
        self.copied.emit(self._value if ok else "")
        return ok


class Divider(QFrame):
    def __init__(self, horizontal: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        if horizontal:
            self.setFixedHeight(1)
            self.setStyleSheet(f"background: {Color.border};")
        else:
            self.setFixedWidth(1)
            self.setStyleSheet(f"background: {Color.border};")


class ConfirmBar(QFrame):
    """内联确认条（规范 §七 ③：按钮就地变「确认」/ 内容区底部浮出确认条）。

    用于「覆盖、删除、清空」这类不可逆操作：不再弹模态框打断流程，
    而是在内容区底部浮出这一条，写清会发生什么，主按钮直接写后果
    （「删除 3 个章节」而不是「确定」）。

    典型用法::

        bar = ConfirmBar(self, "将删除 3 个章节，不可撤销",
                         "删除 3 个章节", "取消")
        bar.confirmed.connect(self._do_delete)
        bar.rejected.connect(bar.hide)
    """

    confirmed = Signal()
    rejected = Signal()

    def __init__(self, parent: QWidget | None = None, text: str = "",
                 ok_text: str = "确认", cancel_text: str = "取消",
                 danger: bool = False):
        super().__init__(parent)
        self.setObjectName("ConfirmBar")
        self.setStyleSheet(
            f"#ConfirmBar {{ background: {Color.card_alt};"
            f"border: 1px solid {Color.border}; border-radius: 8px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 12, 10)
        lay.setSpacing(10)

        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setStyleSheet(
            f"color: {Color.danger if danger else Color.text}; font-size: 12px;")
        lay.addWidget(self.label, 1)

        if cancel_text:
            cancel = QPushButton(cancel_text)
            cancel.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel.setFixedHeight(28)
            cancel.clicked.connect(self._reject)
            lay.addWidget(cancel)
            self._cancel = cancel

        # danger 与否必须在**样式应用前**就定进 kind 属性；后续切换要走
        # set_danger()（unpolish/polish），否则 QSS 选择器不会重新求值 ——
        # 实测确认条主按钮一直是强调绿，红色危险态永远不出现。
        ok = PrimaryButton(ok_text)
        ok.setFixedHeight(28)
        ok.setProperty("kind", "danger" if danger else "primary")
        ok.clicked.connect(self._confirm)
        lay.addWidget(ok)
        self._ok = ok

        self.hide()

    def set_danger(self, danger: bool) -> None:
        """切换主按钮的危险态（规范 §七.3：危险操作主按钮用语义色红）。

        QSS 的属性选择器只在 (un)polish 时求值，改属性后必须重刷样式，
        否则按钮停留在上一次的 kind 上。
        """
        want = "danger" if danger else "primary"
        if self._ok.property("kind") == want:
            return
        self._ok.setProperty("kind", want)
        style = self._ok.style()
        style.unpolish(self._ok)
        style.polish(self._ok)

    def _confirm(self) -> None:
        self.hide()
        self.confirmed.emit()

    def _reject(self) -> None:
        self.hide()
        self.rejected.emit()

    def show_for(self, text: str, ok_text: str = "确认") -> None:
        """更新文案并显示。"""
        self.label.setText(text)
        self._ok.setText(ok_text)
        self.show()


class Menu(QMenu):
    """规范 §五 的白色圆角卡片菜单（条目自绘）。

    Qt 的 QMenu 有两个样式死角，QSS 够不着：

    * **快捷键没有独立样式入口** —— Fusion 风格把快捷键跟正文画成同一个颜色，
      规范要求的 `#8A8A8A` 灰实现不了；
    * **`QMenu::separator` 的 margin 不生效** —— 分隔线全宽通到边框外。

    所以条目干脆全部自己画，几何与配色逐条落实规范：

    * 弹层：白底、1px `#E1E1E1`、圆角 8、内容内边距 5；
    * 条目：悬停 `#F5F5F5` 圆角 4、禁用 0.45 透明度；
    * 图标列：图标墨迹从弹层 x≈17 画到 x≈33（16×16 在 22px 列内居中），
      文本左缘距弹层左缘 48px（1 边框 + 5 内边距 + 42 + 22 图标列（取整后文本左缘 48））；
    * 可勾选项：14×14 强调色勾画在图标列正中，与该项图标互斥显示；
    * 快捷键右对齐 `#8A8A8A`；分隔线 1px `#E1E1E1`、左右各留 10。
    """

    _PAD = 5          # 弹层内容内边距
    _ICON_X = 11      # 条目内图标列起点（弹层坐标 = 1 边框 + 5 内边距 + 11 = 17）
    _ICON_COL = 22    # 图标列宽
    _TEXT_X = 42      # 条目内文本起点（弹层坐标 = 1 + 5 + 42 = 48）

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 黑角/黑线问题（实测踩过两次，第二次才彻底）：
        # ① 弹层默认带系统投影（DWM shadow），和透明弹层的 alpha 合成冲突，
        #    圆角没画到的四个角被合成出纯黑 → NoDropShadowWindowHint 去掉投影；
        # ② 半透明弹层本身就不该用：物理像素 = 逻辑尺寸 × DPR 常常除不尽
        #    （457 × 1.5 = 685.5），窗口最后一行物理像素只被逻辑绘制覆盖一半，
        #    alpha≈0.75 的半透明像素被 DWM 和底下内容混成一条暗线 —— 用户看到
        #    的「菜单最下面一横黑」就是它（垫白板测不出来，浮在深色内容上才现形）。
        #    所以干脆放弃 WA_TranslucentBackground：窗口完全不透明（palette 底色
        #    = 卡片白），任何像素都不存在 alpha<255，DWM 无黑可混；圆角和裁切
        #    全部交给系统级 setMask（见 apply_round_mask）。
        # 注意要用复数 setWindowFlags：PySide6 6.12 里单数 setWindowFlag 对
        # 这个提示位不生效（实测设完 flags 不变）。
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.NoDropShadowWindowHint)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(Color.card))
        self.setPalette(pal)

    def showEvent(self, event):                # noqa: N802 - Qt 命名
        super().showEvent(event)
        self.apply_round_mask()
        # Win11 会自动给弹出窗口套 DWM 圆角裁切，和自绘 8px 圆角叠加会把
        # 卡片角切黑。弹层显示时明确告诉 DWM「不要动我的圆角」。
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                pref = ctypes.c_int(1)          # DWMWCP_DONOTROUND
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd), ctypes.c_uint(33),   # DWMWA_WINDOW_CORNER_PREFERENCE
                    ctypes.byref(pref), ctypes.sizeof(pref))
            except Exception:                   # noqa: BLE001 - 老系统没有 DWM 就跳过
                pass

    def apply_round_mask(self) -> None:
        """系统级圆角裁切（黑角的釜底抽薪）：窗口保持完全不透明（见 __init__），
        setMask 把窗口直接裁成卡片形状，圆角外根本不存在像素，黑角无从产生。
        代价是圆角边缘没有抗锯齿（1px 锯齿，缩放屏上基本看不见）。
        抽成独立方法：test_ui 不依赖真实弹窗，直接调用后断言 mask 形状。"""
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 8, 8)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def paintEvent(self, event):               # noqa: N802 - Qt 命名
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 黑点修补（实测踩过）：窗口必须整面都有人画 —— 卡片只画 0.5px 内缩，
        # 而 mask 的多边形边缘比 AA 弧线多含一两个像素，这些「mask 包含、却没
        # 画到」的像素会露出窗口底色。先把整个矩形填实（全不透明），mask 会把
        # 圆角外的像素裁掉，不怕画出去。
        p.fillRect(self.rect(), QColor(Color.card))

        # ---- 白色圆角卡片：底 + 1px 边框
        card = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(Color.border), 1))
        p.setBrush(QColor(Color.card))
        p.drawRoundedRect(card, 8, 8)

        # 菜单里只要有一个条目带图标/勾选框，所有条目就都按「图标列 + 文本」
        # 对齐（文本左缘 48px）；整份菜单都没有图标时再保留 48px 空列就成了
        # 「左边一大块空白」（实测：简繁菜单只有两项纯文字，被顶得排版很怪），
        # 此时文本按普通内边距摆放。
        self._has_icon_col = any(
            a.isVisible() and (a.isCheckable() or not a.icon().isNull())
            for a in self.actions())

        for action in self.actions():
            if not action.isVisible():
                continue
            rect = self.actionGeometry(action)
            if action.isSeparator():
                # 分隔线：1px，左右各留 10（QSS 的 margin 对它无效）
                y = rect.center().y()
                p.setPen(QPen(QColor(Color.border), 1))
                p.drawLine(QPoint(self._PAD + 5, y), QPoint(self.width() - self._PAD - 5, y))
                continue
            self._draw_item(p, action, rect)
        p.end()

    def _draw_item(self, p: QPainter, action, rect: QRect) -> None:
        hovered = action is self.activeAction() and action.isEnabled()
        if hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(Color.hover))
            p.drawRoundedRect(QRectF(rect).adjusted(1.0, 0.5, -1.0, -0.5), 4, 4)

        use_icon_col = getattr(self, "_has_icon_col", True)
        icon_x = rect.x() + self._ICON_X            # 图标墨迹从弹层 x≈17 起
        text_x = rect.x() + (self._TEXT_X if use_icon_col else 12)

        # ---- 图标列：可勾选项显示强调色勾（与图标互斥），普通项显示 16×16 图标
        if action.isCheckable():
            if action.isChecked():
                pm = icons.pixmap("check", ACCENT, 14)
                p.drawPixmap(icon_x + (self._ICON_COL - 14) // 2,
                             rect.y() + (rect.height() - 14) // 2, pm)
        elif not action.icon().isNull():
            pm = action.icon().pixmap(16, 16)
            p.drawPixmap(icon_x + max(0, (self._ICON_COL - pm.width()) // 2),
                         rect.y() + (rect.height() - pm.height()) // 2, pm)

        # ---- 正文
        p.save()
        p.setFont(self.font())
        if not action.isEnabled():
            p.setOpacity(0.45)
        fm = p.fontMetrics()
        baseline = rect.y() + (rect.height() - fm.height()) // 2 + fm.ascent()
        p.setPen(QColor(Color.text))
        p.drawText(QPoint(text_x, baseline), action.text())
        p.restore()

        # ---- 右侧：快捷键（灰）或子菜单箭头
        if action.menu() is not None:
            cx, cy = rect.right() - 12, rect.center().y()
            p.setPen(QPen(QColor(Color.text_tertiary), 1.6,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.drawLine(cx - 2, cy - 3, cx + 1, cy)
            p.drawLine(cx + 1, cy, cx - 2, cy + 3)
        else:
            shortcuts = action.shortcut()
            if not shortcuts.isEmpty():
                label = QKeySequence(shortcuts[0]).toString(QKeySequence.NativeText)
                font = QFont(self.font())
                font.setPixelSize(max(10, fm.height() - 5))
                p.save()
                p.setFont(font)
                sfm = p.fontMetrics()
                baseline = rect.y() + (rect.height() - sfm.height()) // 2 + sfm.ascent()
                p.setPen(QColor(Color.text_tertiary))
                p.drawText(QPoint(rect.right() - 10 - sfm.horizontalAdvance(label), baseline), label)
                p.restore()


def hbox(*widgets: QWidget, spacing: int = 8, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QWidget:
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for w in widgets:
        lay.addWidget(w)
    return box


__all__ = ["Card", "SectionLabel", "Caption", "CommandButton", "PrimaryButton",
           "IconButton", "SearchBox", "Toast", "Divider", "ConfirmBar", "Menu",
           "hbox"]
