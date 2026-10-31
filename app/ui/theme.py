"""Windows 11 Fluent 设计令牌与全局样式表。

配色遵循 Win11 浅色主题，控件尺寸、圆角、间距参照 Fluent Design 的
4px 栅格：控件圆角 4px、卡片 8px、控件高 32px。

**强调色由程序图标派生**（程序本体设计规范 §三）：唯一品牌色输入 = app.ico，
按钮底色、勾选标记、链接、选中胶囊、输入框聚焦边、进度条全部由图标主色算出；
代码里不出现品牌色字面值（中性灰阶除外）。换图标整套界面跟着换。
"""

from __future__ import annotations

import os
import sys
import tempfile

from ..core.accent import palette as _icon_palette


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
    # selection 已按规范 §三 改由图标派生（ACCENT_SOFT），不再写死 #CCE4F7；
    # success 未使用，已删除 —— 语义色只保留 danger / warning（规范 §七.2）。
    danger = "#C42B1C"
    warning = "#9D5D00"


# ------------------------------------------------------------------ 品牌色
#: 由 app.ico 派生的四个用途色（规范 §三 的公式表）。
#: 换图标整套界面跟着换；取不到主色时走固定种子，与正常路径同一套派生函数。
#:
#: 取色走 app/core/accent.py（Qt 的 ICO 插件读图，QImage 不需要 QGuiApplication）
#: —— 所以在 import 期就能安全求值，不依赖 QApplication 是否已建。
_PALETTE = _icon_palette()

#: 强调色（主按钮底、勾选、链接、选中胶囊、输入框聚焦边、进度条）
ACCENT = _PALETTE["accent"]
#: 强调暗（按下态）
ACCENT_DARK = _PALETTE["dark"]
#: 浅底（选中胶囊、轻提示）
ACCENT_SOFT = _PALETTE["soft"]
#: 微光悬停
ACCENT_HOVER_BG = _PALETTE["hover"]


def accent_color() -> str:
    """强调色（函数形式，供 stylesheet() 内部取用）。"""
    return _PALETTE["accent"]


FONT_FAMILY = "Microsoft YaHei UI"
MONO_FAMILY = "Microsoft YaHei UI"


def mix(hex_a: str, hex_b: str, ratio: float) -> str:
    """按比例混合两个颜色（用于生成 hover / pressed 态）。"""
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    out = [round(x + (y - x) * ratio) for x, y in zip(a, b)]
    return "#{:02X}{:02X}{:02X}".format(*out)


def accent_hover() -> str:
    """强调色悬停态（提亮一档）。"""
    return mix(ACCENT, "#FFFFFF", 0.10)


def accent_pressed() -> str:
    """强调色按下态（压暗一档）。"""
    return mix(ACCENT, "#000000", 0.12)


ACCENT_HOVER = accent_hover()
ACCENT_PRESSED = accent_pressed()


# ------------------------------------------------------------------ 样式表
def stylesheet() -> str:
    # 原先有个 scale 参数，从未有调用方传过值（全是 stylesheet()），
    # 留着只会让人以为支持缩放 —— 高 DPI 由 Qt 统一处理，删掉。
    s = lambda v: max(1, round(v))          # noqa: E731
    # 强调色在这里才取值 —— stylesheet() 一定在 QApplication 之后才被调用
    ACCENT = accent_color()
    ACCENT_HOVER = accent_hover()
    ACCENT_PRESSED = accent_pressed()
    ACCENT_SOFT = _PALETTE["soft"]
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

/* 危险操作的主按钮（规范 §七.3）：语义色红底白字，悬停不变色、按下加深 */
QPushButton[kind="danger"] {{
    background: {Color.danger};
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}}
QPushButton[kind="danger"]:hover {{ background: {Color.danger}; }}
QPushButton[kind="danger"]:pressed {{ background: {mix(Color.danger, "#000000", 0.15)}; }}
QPushButton[kind="danger"]:disabled {{ background: {Color.border_strong}; color: #FFFFFF; }}
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
    selection-background-color: {ACCENT_SOFT};
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
    /* 内边距让条目从容器圆角/边框里缩进一圈：原先条目通到边上，
       选中项的外框贴着弹层边框，看着像套了两层框 */
    padding: {s(4)}px;
    margin: 0px;
    outline: 0px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {Color.text};
}}
QComboBox QAbstractItemView::item {{
    min-height: {s(26)}px;
    padding: {s(3)}px {s(10)}px;
    border: none;
    border-radius: {s(4)}px;
}}
QComboBox QAbstractItemView::item:hover {{ background: {Color.hover}; }}
QComboBox QAbstractItemView::item:selected {{
    background: {ACCENT_SOFT};
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
    background: {ACCENT_SOFT};
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


# ------------------------------------------------------------------ DWM 标题栏
def apply_dwm_chrome(hwnd: int | None = None) -> None:
    """按《程序本体设计规范》§四定制系统标题栏（主窗口与所有对话框共用）。

    caption 色与内容区底色一致，标题栏和内容区看起来是一体的；
    border 比 caption 深一档，看得见窗口边界但不刺眼。
    Win11 的 DWM 用 COLORREF（0x00BBGGRR），不是 RGB —— 顺序别写反。
    老系统不支持就静默跳过，不崩。
    """
    if sys.platform != "win32" or not hwnd:
        return

    def rgb(r: int, g: int, b: int) -> int:
        return (b << 16) | (g << 8) | r

    try:
        import ctypes

        def hex_to_colorref(value: str) -> int:
            value = value.lstrip("#")
            r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
            return rgb(r, g, b)

        dwmapi = ctypes.WinDLL("dwmapi")
        handle = hwnd

        def set_attr(attr: int, value: int) -> None:
            v = ctypes.c_int(value)
            dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(handle), ctypes.c_uint(attr),
                                         ctypes.byref(v), ctypes.sizeof(v))

        set_attr(20, 0)                                  # DWMWA_USE_IMMERSIVE_DARK_MODE = 浅色
        set_attr(33, 2)                                  # 圆角
        set_attr(34, hex_to_colorref("#E8E8E8"))         # 边框色，比 caption 深一档
        set_attr(35, hex_to_colorref(Color.window))      # caption = 内容区底色 #F3F3F3
        set_attr(36, hex_to_colorref(Color.text))        # 标题文字 #1B1B1B
        set_attr(38, 0)                                  # 保持纯色背景，保证文字可读
    except Exception:       # noqa: BLE001 - 老系统上失败不影响使用
        pass


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
    selection-background-color: {ACCENT_SOFT};
    selection-color: {Color.text};
    color: {Color.text};
}}
"""


__all__ = ["Color", "ACCENT", "ACCENT_HOVER", "ACCENT_PRESSED", "FONT_FAMILY",
           "stylesheet", "editor_font_qss", "mix", "apply_dwm_chrome",
           "accent_color", "accent_hover", "accent_pressed"]
