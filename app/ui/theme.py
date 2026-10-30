"""Windows 11 Fluent 设计令牌与全局样式表。

配色遵循 Win11 浅色主题（与系统强调色联动），控件尺寸、圆角、间距
参照 Fluent Design 的 4px 栅格：控件圆角 4px、卡片 8px、控件高 32px。
"""

from __future__ import annotations

import os
import sys
import tempfile

try:                                     # 仅 Windows 有 winreg
    import winreg
except ImportError:                      # pragma: no cover
    winreg = None  # type: ignore


def _assets_dir() -> str:
    base = os.environ.get("APPDATA") or tempfile.gettempdir()
    path = os.path.join(base, "txtFormat", "assets")
    os.makedirs(path, exist_ok=True)
    return path


_TICK_PATH: str | None = None


def tick_icon_path() -> str:
    """生成勾选标记 PNG（QSS 的 image: url() 只能引用文件）。"""
    global _TICK_PATH
    if _TICK_PATH and os.path.exists(_TICK_PATH):
        return _TICK_PATH
    path = os.path.join(_assets_dir(), "check.png")
    if not os.path.exists(path):
        from PySide6.QtCore import QByteArray, QRectF, Qt
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtSvg import QSvgRenderer

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" '
            'fill="none" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" '
            'stroke-linejoin="round"><path d="M3.5 8.4l3 3 5.8-6.2"/></svg>'
        )
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, 32, 32))
        painter.end()
        pm.save(path, "PNG")
    _TICK_PATH = path.replace("\\", "/")
    return _TICK_PATH


# ------------------------------------------------------------------ 颜色
class Color:
    window = "#F3F3F3"
    card = "#FFFFFF"
    card_alt = "#FAFAFA"
    border = "#E1E1E1"
    border_strong = "#D6D6D6"
    text = "#1B1B1B"
    text_secondary = "#5C5C5C"
    text_tertiary = "#8A8A8A"
    hover = "#F5F5F5"
    pressed = "#EBEBEB"
    hoverline = "#E8E8E8"
    disabled = "#B5B5B5"
    editor_bg = "#FFFFFF"
    selection = "#CCE4F7"
    accent_fallback = "#0067C0"
    danger = "#C42B1C"
    success = "#0F7B0F"
    warning = "#9D5D00"


def _system_accent() -> str:
    """读取系统强调色（AccentColor 为 ABGR）。"""
    if winreg is None or sys.platform != "win32":
        return Color.accent_fallback
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as key:
            value, _ = winreg.QueryValueEx(key, "AccentColor")
        b = value & 0xFF
        g = (value >> 8) & 0xFF
        r = (value >> 16) & 0xFF
        # 太亮/太灰的强调色在浅色主题下可读性差，退回默认蓝
        if r + g + b < 180 or (r > 235 and g > 235 and b > 235):
            return Color.accent_fallback
        return f"#{r:02X}{g:02X}{b:02X}"
    except OSError:
        return Color.accent_fallback


ACCENT = _system_accent()
FONT_FAMILY = "Microsoft YaHei UI"
MONO_FAMILY = "Microsoft YaHei UI"


def mix(hex_a: str, hex_b: str, ratio: float) -> str:
    """按比例混合两个颜色（用于生成 hover / pressed 态）。"""
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    out = [round(x + (y - x) * ratio) for x, y in zip(a, b)]
    return "#{:02X}{:02X}{:02X}".format(*out)


ACCENT_HOVER = mix(ACCENT, "#FFFFFF", 0.10)
ACCENT_PRESSED = mix(ACCENT, "#000000", 0.12)


# ------------------------------------------------------------------ 样式表
def stylesheet(scale: float = 1.0) -> str:
    s = lambda v: max(1, round(v * scale))          # noqa: E731
    return f"""
* {{
    font-family: "{FONT_FAMILY}";
    font-size: {s(12)}px;
    outline: none;
}}
QWidget {{
    color: {Color.text};
    background: transparent;
}}
QMainWindow, QDialog {{
    background: {Color.window};
}}
QToolTip {{
    background: {Color.card};
    color: {Color.text};
    border: 1px solid {Color.border};
    border-radius: {s(6)}px;
    padding: {s(6)}px {s(9)}px;
}}

/* -------------------------------------------------- 菜单栏 */
QMenuBar {{
    background: {Color.window};
    border: none;
    padding: {s(2)}px {s(8)}px;
}}
QMenuBar::item {{
    background: transparent;
    padding: {s(5)}px {s(10)}px;
    border-radius: {s(4)}px;
    color: {Color.text};
}}
QMenuBar::item:selected {{ background: {Color.hover}; }}
QMenuBar::item:pressed {{ background: {Color.pressed}; }}

QMenu {{
    background: {Color.card};
    border: 1px solid {Color.border};
    border-radius: {s(8)}px;
    padding: {s(5)}px;
}}
QMenu::item {{
    padding: {s(7)}px {s(28)}px {s(7)}px {s(14)}px;
    border-radius: {s(4)}px;
    color: {Color.text};
}}
QMenu::item:selected {{ background: {Color.hover}; }}
QMenu::item:disabled {{ color: {Color.disabled}; }}
QMenu::separator {{
    height: 1px;
    background: {Color.border};
    margin: {s(5)}px {s(10)}px;
}}
QMenu::indicator {{ width: {s(14)}px; height: {s(14)}px; left: {s(7)}px; }}

/* -------------------------------------------------- 按钮 */
QPushButton {{
    background: {Color.card};
    border: 1px solid {Color.border};
    border-radius: {s(4)}px;
    padding: {s(5)}px {s(14)}px;
    min-height: {s(22)}px;
    color: {Color.text};
}}
QPushButton:hover {{ background: {Color.hover}; border-color: {Color.border_strong}; }}
QPushButton:pressed {{ background: {Color.pressed}; color: {Color.text_secondary}; }}
QPushButton:disabled {{ color: {Color.disabled}; background: {Color.card_alt}; border-color: {Color.border}; }}
QPushButton:default {{ border-color: {ACCENT}; }}

QPushButton[kind="primary"] {{
    background: {ACCENT};
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[kind="primary"]:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton[kind="primary"]:disabled {{ background: {Color.border_strong}; color: #FFFFFF; }}

QPushButton[kind="subtle"] {{
    background: transparent;
    border: 1px solid transparent;
}}
QPushButton[kind="subtle"]:hover {{ background: {Color.hover}; }}
QPushButton[kind="subtle"]:pressed {{ background: {Color.pressed}; }}

QPushButton[kind="danger"] {{ color: {Color.danger}; border-color: {Color.border}; }}
QPushButton[kind="danger"]:hover {{ background: #FDF3F2; }}
QPushButton[compact="true"] {{ padding: {s(5)}px {s(6)}px; }}
QPushButton[compact="true"]:checked {{
    background: {mix(ACCENT, "#FFFFFF", 0.86)};
    border: 1px solid {ACCENT};
    color: {Color.text};
}}
QPushButton[compact="true"]:checked:hover {{
    background: {mix(ACCENT, "#FFFFFF", 0.80)};
}}

/* -------------------------------------------------- 输入控件 */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit, QListWidget, QTreeWidget, QTableWidget {{
    background: {Color.card};
    border: 1px solid {Color.border};
    border-radius: {s(4)}px;
    selection-background-color: {Color.selection};
    selection-color: {Color.text};
}}
QLineEdit {{ padding: {s(5)}px {s(9)}px; min-height: {s(22)}px; }}
/* 串替换里的多行输入框：与单行框同款外观，但允许折行显示长正则 */
QPlainTextEdit[role="multiline-input"] {{
    padding: {s(6)}px {s(9)}px;
    font-size: {s(12)}px;
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {Color.border_strong}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
}}
QLineEdit:disabled, QComboBox:disabled {{ color: {Color.disabled}; background: {Color.card_alt}; }}

QComboBox {{ padding: {s(4)}px {s(9)}px; min-height: {s(24)}px; }}
QComboBox::drop-down {{ border: none; width: {s(26)}px; }}
/* 弹层：边框与圆角交给容器（QComboBoxPrivateContainer）画，
   列表视图自身不画边框/内边距——两处都画就会出现"双层边框 + 缺角"的错层。
   容器里那条 QComboBoxPrivateScroller 横带由 CompactComboBox 在运行时代码移除。 */
QComboBoxPrivateContainer {{
    background: {Color.card};
    border: 1px solid {Color.border};
    border-radius: {s(8)}px;
    padding: 0px;
    margin: 0px;
}}
QComboBox QAbstractItemView {{
    background: {Color.card};
    border: none;
    border-radius: 0px;
    padding: 0px;
    margin: 0px;
    outline: 0px;
    selection-background-color: {Color.selection};
    selection-color: {Color.text};
}}
QComboBox QAbstractItemView::item {{
    min-height: {s(26)}px;
    padding: {s(3)}px {s(10)}px;
    border: none;
}}
QComboBox QAbstractItemView::item:hover {{ background: {Color.hover}; }}
QComboBox QAbstractItemView::item:selected {{
    background: {Color.selection};
    color: {Color.text};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: {s(18)}px;
    border: none;
    background: transparent;
}}

/* -------------------------------------------------- 单选/复选 */
QCheckBox, QRadioButton {{ spacing: {s(8)}px; color: {Color.text}; padding: {s(2)}px 0; }}
QCheckBox::indicator {{
    width: {s(16)}px; height: {s(16)}px;
    border: 1px solid {Color.border_strong};
    border-radius: {s(4)}px;
    background: {Color.card};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url({tick_icon_path()});
}}
QRadioButton::indicator {{
    width: {s(16)}px; height: {s(16)}px;
    border: 1px solid {Color.border_strong};
    border-radius: {s(8)}px;
    background: {Color.card};
}}
QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QRadioButton::indicator:checked {{
    border: 1px solid {ACCENT};
    border-radius: {s(8)}px;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                stop:0 {ACCENT}, stop:0.42 {ACCENT}, stop:0.5 #FFFFFF, stop:1 #FFFFFF);
}}

/* -------------------------------------------------- 列表/表格 */
QListWidget, QTreeWidget, QTableWidget {{
    border: 1px solid {Color.border};
    border-radius: {s(6)}px;
    background: {Color.card};
    alternate-background-color: {Color.card_alt};
}}
QListWidget::item, QTreeWidget::item {{
    padding: {s(4)}px {s(6)}px;
    border-radius: {s(4)}px;
}}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {Color.hover}; }}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background: {Color.selection};
    color: {Color.text};
}}
/* 常用正则表达式：常驻固定列表，行高固定、不出现横向滚动条 */
QListWidget[role="regex-list"] {{
    border: 1px solid {Color.border};
    border-radius: {s(6)}px;
    background: {Color.card};
    padding: {s(2)}px;
    outline: none;
    font-size: {s(12)}px;
}}
QListWidget[role="regex-list"]::item {{
    padding: 0 {s(6)}px;
    border-radius: {s(4)}px;
}}
QHeaderView::section {{
    background: {Color.card_alt};
    color: {Color.text_secondary};
    border: none;
    border-bottom: 1px solid {Color.border};
    padding: {s(5)}px {s(6)}px;
    font-weight: 600;
}}
QTableWidget {{ gridline-color: {Color.border}; font-size: {s(11)}px; }}
QTableWidget::item {{ padding: {s(3)}px {s(3)}px; }}

/* -------------------------------------------------- 分组框 */
QGroupBox {{
    border: 1px solid {Color.border};
    border-radius: {s(8)}px;
    margin-top: {s(14)}px;
    padding: {s(12)}px {s(10)}px {s(8)}px {s(10)}px;
    background: {Color.card};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {s(10)}px;
    padding: 0 {s(5)}px;
    color: {Color.text_secondary};
}}

/* -------------------------------------------------- 滚动条 */
QScrollBar:vertical {{
    background: transparent; width: {s(12)}px; margin: {s(2)}px;
}}
QScrollBar::handle:vertical {{
    background: #C9C9C9; border-radius: {s(3)}px; min-height: {s(28)}px;
}}
QScrollBar::handle:vertical:hover {{ background: #A8A8A8; }}
QScrollBar:horizontal {{
    background: transparent; height: {s(12)}px; margin: {s(2)}px;
}}
QScrollBar::handle:horizontal {{
    background: #C9C9C9; border-radius: {s(3)}px; min-width: {s(28)}px;
}}
QScrollBar::handle:horizontal:hover {{ background: #A8A8A8; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* -------------------------------------------------- 其它 */
QStatusBar {{
    background: {Color.window};
    border-top: 1px solid {Color.border};
    color: {Color.text_secondary};
}}
QStatusBar::item {{ border: none; }}

QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{
    background: transparent;
    padding: {s(6)}px {s(14)}px;
    margin-right: {s(4)}px;
    border-radius: {s(4)}px;
    color: {Color.text_secondary};
}}
QTabBar::tab:hover {{ background: {Color.hover}; }}
QTabBar::tab:selected {{
    color: {Color.text};
    background: {Color.card};
    border-bottom: 2px solid {ACCENT};
    font-weight: 600;
}}

QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {Color.border}; }}
QSplitter::handle:horizontal {{ width: {s(6)}px; }}
QSplitter::handle:vertical {{ height: {s(6)}px; }}

QProgressBar {{
    border: none; border-radius: {s(3)}px;
    background: {Color.hover}; height: {s(4)}px; text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: {s(3)}px; }}

QScrollArea {{ border: none; background: transparent; }}
QFrame#Card {{
    background: {Color.card};
    border: 1px solid {Color.border};
    border-radius: {s(8)}px;
}}
QLabel[role="title"] {{ font-size: {s(19)}px; font-weight: 600; }}
QLabel[role="subtitle"] {{ font-size: {s(13)}px; color: {Color.text_secondary}; }}
QLabel[role="caption"] {{ color: {Color.text_secondary}; font-size: {s(11)}px; }}
QLabel[role="hint"] {{ color: {Color.text_tertiary}; font-size: {s(11)}px; }}
"""


def editor_font_qss(family: str, size_pt: float, line_percent: int) -> str:
    return f"""
QPlainTextEdit[role="editor"] {{
    background: {Color.editor_bg};
    border: 1px solid {Color.border};
    border-radius: 8px;
    padding: 10px 14px;
    font-family: "{family}";
    font-size: {size_pt:.1f}pt;
    line-height: {line_percent}%;
    selection-background-color: {Color.selection};
    selection-color: {Color.text};
    color: {Color.text};
}}
"""


__all__ = ["Color", "ACCENT", "ACCENT_HOVER", "ACCENT_PRESSED", "FONT_FAMILY",
           "stylesheet", "editor_font_qss", "mix"]
