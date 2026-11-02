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
_ARROWS: dict[str, str] = {}          # 文件名 → 绝对路径缓存


def _arrow_png(name: str, angle: float, filename: str) -> str:
    """把 icons 表里的 ``next``（右箭头）旋转 ``angle`` 度存成 PNG，返回路径。

    QSS 的 ``image: url()`` 只能引用文件，所以箭头都要先落盘；生成手法与
    :func:`tick_icon_path` 相同。QSS 定制过 drop-down / 上下按钮后 Qt 不再
    画默认箭头（实测：下拉框看着像输入框、字号框没有微调箭头），箭头不许
    另画 —— 全部从同一支右箭头旋转得来，笔画粗细与全套图标一致。
    """
    cached = _ARROWS.get(filename)
    if cached and os.path.exists(cached):
        return cached
    path = os.path.join(_assets_dir(), filename)
    if not os.path.exists(path):
        from PySide6.QtGui import QTransform

        from . import icons          # 局部导入：icons.py 反过来要 import 本模块的 Color/ACCENT

        pm = icons.pixmap("next", Color.text_secondary, 13)
        arrow = pm.transformed(QTransform().rotate(angle))
        arrow.save(path, "PNG")
    full = path.replace("\\", "/")
    _ARROWS[filename] = full
    return full


def combo_arrow_path() -> str:
    """下拉框的向下箭头 PNG 路径（右箭头顺时针转 90°）。"""
    return _arrow_png("next", 90, "combo_arrow.png")


def spin_arrow_path(direction: str) -> str:
    """SpinBox 微调按钮的箭头 PNG 路径：``up`` 逆时针 90°、``down`` 顺时针 90°。"""
    if direction == "up":
        return _arrow_png("next", -90, "spin_up.png")
    if direction == "down":
        return _arrow_png("next", 90, "spin_down.png")
    raise ValueError(f"未知方向: {direction}")


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

        from . import icons          # 局部导入：icons.py 反过来要 import 本模块的 Color/ACCENT

        # 勾就是 icons 里的 check（《图标规范》§七：不许另画一个勾）。
        # 笔宽按 16px 算（1.575），再放大 2 倍渲染 —— 同 pixmap() 的超采样手法。
        renderer = QSvgRenderer(QByteArray(icons.svg("check", "#FFFFFF", 16).encode("utf-8")))
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
    # 状态栏比窗口底色深一档（规范 §六：状态栏是「运行仪表」，得和内容区分开）。
    # 窗口底 #F3F3F3 → 状态栏 #EEEEEE + 上边线 #E0E0E0，仍在同一套灰阶里。
    status_bg = "#EEEEEE"
    status_line = "#E0E0E0"
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
#: 浅底（选中胶囊、轻提示）
ACCENT_SOFT = _PALETTE["soft"]
# 曾在这里导出 ACCENT_DARK 与 ACCENT_HOVER_BG，全仓各只用了一次（就是定义那一行）：
# 前者被 ACCENT_PRESSED 取代，后者在规范 §八 明令「实心主按钮悬停不变色」后失去用途。
# 留着会让下次换图标时白算一遍，也让人误以为界面上真的用到了。


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


def accent_pressed() -> str:
    """强调色按下态（压暗一档）。"""
    return mix(ACCENT, "#000000", 0.12)


# 曾经还有个 accent_hover()（提亮 10%）—— 已删除：规范 §八 要求
# 「实心主按钮悬停**不变色**，只有按下时加深」，提亮会让实心块像状态翻转。
ACCENT_PRESSED = accent_pressed()


# ------------------------------------------------------------------ 样式表
def stylesheet() -> str:
    # 原先有个 scale 参数，从未有调用方传过值（全是 stylesheet()），
    # 留着只会让人以为支持缩放 —— 高 DPI 由 Qt 统一处理，删掉。
    s = lambda v: max(1, round(v))          # noqa: E731
    # 强调色在这里才取值 —— stylesheet() 一定在 QApplication 之后才被调用
    ACCENT = accent_color()
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
/* 悬停**保持原色**（规范 §八）：实心色块一变亮就像状态翻转，会被当成 bug。
   必须显式写回 ACCENT —— 否则会掉进下面通用的 QPushButton:hover，变成浅灰底。 */
QPushButton[kind="primary"]:hover {{ background: {ACCENT}; }}
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
/* 定制过 ::drop-down 后 Qt 不再画默认箭头（不写这条，所有下拉框看着像
   输入框 —— 字体选择框被当成「有问题」报过）。箭头 = icons 的 next 旋转 90°。 */
QComboBox::down-arrow {{
    width: {s(10)}px; height: {s(10)}px;
    image: url({combo_arrow_path()});
}}
/* 弹层：边框画在列表视图上（radius 7），容器只铺白底并把整个卡片内收
   1px（CompactComboBox 设置布局边距）。两条弧同心：mask 8px（窗口）→
   视图边框 7px（内收 1px）。边框不画在容器窗口边缘的原因见 widgets.py ——
   最外 1px 会被 DWM 栅格化吃掉（右缘整个消失）。
   另：app 级 ``QComboBoxPrivateContainer`` 选择器匹配不到私有容器（死代码），
   别再往那儿写样式。 */
QComboBox QAbstractItemView {{
    background: {Color.card};
    border: 1px solid {Color.border};
    border-radius: {s(7)}px;
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
/* 定制过 up/down 按钮后 Qt 不画默认箭头（字号框曾被当成「坏了」）。
   两支箭头同样由 icons 的 next 旋转得来，不另画图标。 */
QSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: {s(17)}px; border: none; background: transparent;
}}
QSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: {s(17)}px; border: none; background: transparent;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {Color.hover}; }}
QSpinBox::up-arrow {{
    image: url({spin_arrow_path("up")}); width: {s(9)}px; height: {s(9)}px;
}}
QSpinBox::down-arrow {{
    image: url({spin_arrow_path("down")}); width: {s(9)}px; height: {s(9)}px;
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
/* 字体选择器的族名列表：每条用自身字体渲染（FontRole），行高必须统一 ——
   不同字体的行高天然差 1~3px，不钉死就会参差不齐 */
QListWidget#FontList {{ padding: {s(4)}px; }}
QListWidget#FontList::item {{
    min-height: {s(24)}px;
    padding: {s(3)}px {s(8)}px;
    border-radius: {s(4)}px;
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
    background: {Color.status_bg};
    border-top: 1px solid {Color.status_line};
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


def editor_font_qss(family: str, size_pt: float, line_percent: int,
                    weight: int = 400, italic: bool = False) -> str:
    style = "italic" if italic else "normal"
    return f"""
QPlainTextEdit[role="editor"] {{
    background: {Color.editor_bg};
    border: 1px solid {Color.border};
    border-radius: 8px;
    padding: 10px 14px;
    font-family: "{family}";
    font-size: {size_pt:.1f}pt;
    font-weight: {int(weight)};
    font-style: {style};
    line-height: {line_percent}%;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {Color.text};
    color: {Color.text};
}}
"""


__all__ = ["Color", "ACCENT", "ACCENT_PRESSED", "FONT_FAMILY",
           "stylesheet", "editor_font_qss", "mix", "apply_dwm_chrome",
           "accent_color", "accent_pressed"]
