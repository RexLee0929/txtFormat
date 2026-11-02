"""内置 SVG 图标：24×24 栅格线性图标，路径来自 ``icons/Unified``（《图标规范》）。

表里**只有几何** —— 一条 ``<path>`` = 路径数据（实心块另带 ``fill``），没有颜色、
没有尺寸、没有用途；颜色与尺寸都是调用时给的（规范 §六.1）。

两件事必须分开算（§三.1）：

* **画多大** = 24 栅格整体缩到 N px，缩放比恒为 ``N/24``。SVG 里写
  ``width/height=size`` 且 ``viewBox="0 0 24 24"``，缩放比由渲染器算，不是按墨迹外框拉伸。
* **线描多粗** = 素材标称 1.4 也要乘同一个 ``N/24``；乘完低于 1.05 物理像素就加粗，
  否则 16px 下那条线会塌成一层浅灰（§三.2 的实测：原值 1.4 在 16px 只剩 0% 实心像素）。
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import ACCENT, Color

#: 允许的渲染尺寸（《图标规范》§三.4 的档位表）—— 出现 15/17/22 这种就是随手写的
SIZES: tuple[int, ...] = (13, 14, 16, 18, 20, 24, 32)

#: 键名 → 该图标的全部 ``<path>``（实心块带 ``fill="currentColor" stroke="none"``）。
#: 只放程序真正用到的键；没被引用的键不许留在表里当「备用」（§八.2）。
_PATHS: dict[str, str] = {
    "about": '<path d="M12 3C16.9706 3 21 7.02944 21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3Z"/><path d="M12 3v3.2M12 17.8V21M3 12h3.2M17.8 12H21"/><path d="M12 11v5.5"/><path d="M12 8h.01"/>',
    "case": '<path d="M2.5 18.5L7 6l4.5 12.5"/><path d="M4.1 14.5h5.8"/><path d="M21 13.2a3.2 3.2 0 1 0-3.2 5.3"/><path d="M21 11v7.5"/>',
    "check": '<path d="M4.5 12.5l5 5L19.5 7"/>',
    "clean": '<path d="M8 20A1.5 1.5 0 0 1 5.44 18.94L4.86 18.36A1.92 1.92 0 0 1 4.86 15.64L12.14 8.36A1.92 1.92 0 0 1 14.86 8.36L18.14 11.64A1.92 1.92 0 0 1 17.93 14.1L10.73 19.14A1.5 1.5 0 0 1 8 20Z"/><path d="M8.6 12.9l5.4 5.4"/><path d="M3 22h18"/>',
    "close": '<path d="M5.5 5.5l13 13M18.5 5.5l-13 13"/>',
    "convert": '<path d="M4.92 6.5L8.08 6.5C9.14039 6.5 10 7.35961 10 8.42L10 15.58C10 16.6404 9.14039 17.5 8.08 17.5L4.92 17.5C3.85961 17.5 3 16.6404 3 15.58L3 8.42C3 7.35961 3.85961 6.5 4.92 6.5Z"/><path d="M15.92 6.5L19.08 6.5C20.1404 6.5 21 7.35961 21 8.42L21 15.58C21 16.6404 20.1404 17.5 19.08 17.5L15.92 17.5C14.8596 17.5 14 16.6404 14 15.58L14 8.42C14 7.35961 14.8596 6.5 15.92 6.5Z"/><path d="M10 12h4"/><path d="M12.3 9.8l2.2 2.2-2.2 2.2"/>',
    "copy": '<path d="M11.4 9L18.6 9C19.9255 9 21 10.0745 21 11.4L21 18.6C21 19.9255 19.9255 21 18.6 21L11.4 21C10.0745 21 9 19.9255 9 18.6L9 11.4C9 10.0745 10.0745 9 11.4 9Z"/><path d="M15 9V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h3"/>',
    "edit": '<path d="M4 20L4.63 16.71A1.44 1.44 0 0 1 5.92 14.28L14.58 5.62A1.44 1.44 0 0 1 16.62 5.62L18.38 7.38A1.44 1.44 0 0 1 18.38 9.42L9.72 18.08A1.44 1.44 0 0 1 7.29 19.37Z"/><path d="M6.9 13.6l3.5 3.5"/>',
    "error": '<path d="M12 3C16.9706 3 21 7.02944 21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3Z"/><path d="M12 7.4v6"/><path d="M12 17h.01"/>',
    "file": '<path d="M5 5.4A2.4 2.4 0 0 1 7.4 3L14 3L19 8L19 18.6A2.4 2.4 0 0 1 16.6 21L7.4 21A2.4 2.4 0 0 1 5 18.6Z"/><path d="M14 3v5h5"/>',
    "font": '<path d="M6 19.5L12 4.5l6 15"/><path d="M8.4 14.5h7.2"/>',
    "folder": '<path d="M3 9.4A2.4 2.4 0 0 1 5.4 7L7.59 7A1.41 1.41 0 0 1 10 8L10 8A1.41 1.41 0 0 0 12.41 9L18.6 9A2.4 2.4 0 0 1 21 11.4L21 17.6A2.4 2.4 0 0 1 18.6 20L5.4 20A2.4 2.4 0 0 1 3 17.6Z"/>',
    "format": '<path d="M4 5h16M4 9.5h10M4 14h16M4 18.5h10"/>',
    "goto": '<path d="M3.5 6.5h17M3.5 12h9M3.5 17.5h9"/><path d="M15 12h6"/><path d="M18.5 8.5l3.5 3.5-3.5 3.5"/>',
    "indent": '<path d="M3.5 5h17M9.5 10h11M9.5 15h11M3.5 20h17"/><path d="M3.5 9.5l3 3-3 3"/>',
    "info": '<path d="M12 3C16.9706 3 21 7.02944 21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3Z"/><path d="M12 11.2v5.8"/><path d="M12 7.8h.01"/>',
    "insert": '<path d="M3 6.42A1.92 1.92 0 0 1 4.92 4.5L13.08 4.5A1.92 1.92 0 0 1 15 6.42L15 17.58A1.92 1.92 0 0 1 13.08 19.5L4.92 19.5A1.92 1.92 0 0 1 3 17.58Z"/><path d="M7 9.5h5M7 14.5h5"/><path d="M18 12h4"/><path d="M19 9.5l2.5 2.5-2.5 2.5"/>',
    "list": '<path d="M8.5 6h12.5M8.5 12h12.5M8.5 18h12.5"/><path d="M4 6h.01"/><path d="M4 12h.01"/><path d="M4 18h.01"/>',
    "mail": '<path d="M5.4 5.5L18.6 5.5C19.9255 5.5 21 6.57452 21 7.9L21 16.1C21 17.4255 19.9255 18.5 18.6 18.5L5.4 18.5C4.07452 18.5 3 17.4255 3 16.1L3 7.9C3 6.57452 4.07452 5.5 5.4 5.5Z"/><path d="M3.4 7.2l7.4 5.3a2 2 0 0 0 2.4 0l7.4-5.3"/>',
    "merge": '<path d="M4 4v4.5a3.5 3.5 0 0 0 3.5 3.5h9"/><path d="M4 20v-4.5a3.5 3.5 0 0 1 3.5-3.5h9"/><path d="M13.5 8.5l3.5 3.5-3.5 3.5"/>',
    "new": '<path d="M5 5.4A2.4 2.4 0 0 1 7.4 3L14 3L19 8L19 18.6A2.4 2.4 0 0 1 16.6 21L7.4 21A2.4 2.4 0 0 1 5 18.6Z"/><path d="M14 3v5h5"/><path d="M12 10.5v6M9 13.5h6"/>',
    "next": '<path d="M9 5.5L15.5 12 9 18.5"/>',
    "open": '<path d="M3 9.4A2.4 2.4 0 0 1 5.4 7L7.59 7A1.41 1.41 0 0 1 10 8L10 8A1.41 1.41 0 0 0 12.41 9L18.6 9A2.4 2.4 0 0 1 21 11.4L21 17.6A2.4 2.4 0 0 1 18.6 20L5.4 20A2.4 2.4 0 0 1 3 17.6Z"/><path d="M9 14.5h7"/><path d="M13.5 11.8l3 2.7-3 2.7"/>',
    "outdent": '<path d="M3.5 5h17M9.5 10h11M9.5 15h11M3.5 20h17"/><path d="M6.5 9.5l-3 3 3 3"/>',
    "pin": '<path d="M12 11.6V20.5"/><path d="M9.2 4.7A1.2 1.2 0 0 1 10.4 3.5L13.6 3.5A1.2 1.2 0 0 1 14.8 4.7L14.8 7.2A1.2 1.2 0 0 0 15.59 9.3L16.81 10.7A1.2 1.2 0 0 1 16.4 11.6L7.6 11.6A1.2 1.2 0 0 1 7.19 10.7L8.41 9.3A1.2 1.2 0 0 0 9.2 7.2Z"/>',
    "play": '<path d="M8 5.92A1.92 1.92 0 0 1 9.6 5.07L18.4 10.93A1.92 1.92 0 0 1 18.4 13.07L9.6 18.93A1.92 1.92 0 0 1 8 18.08Z"/>',
    "plus": '<path d="M12 4.5v15M4.5 12h15"/>',
    "prev": '<path d="M15 5.5L8.5 12 15 18.5"/>',
    "read": '<path d="M12 6.6C10 4.9 7.4 4.3 4 4.3v13.9c3.4 0 6 .6 8 2.3 2-1.7 4.6-2.3 8-2.3V4.3c-3.4 0-6 .6-8 2.3z"/><path d="M12 6.6v13.9"/>',
    "redo": '<path d="M20 9h-9.5a5.5 5.5 0 0 0 0 11h6"/><path d="M16 4.5L20.5 9 16 13.5"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20 4.5V10h-5.5"/>',
    "replace": '<path d="M3.5 8.5h13.5"/><path d="M14 5.5l3 3-3 3"/><path d="M20.5 15.5H7"/><path d="M10 12.5l-3 3 3 3"/>',
    "rulers": '<path d="M3.94 8L20.06 8C20.8553 8 21.5 8.64471 21.5 9.44L21.5 14.56C21.5 15.3553 20.8553 16 20.06 16L3.94 16C3.14471 16 2.5 15.3553 2.5 14.56L2.5 9.44C2.5 8.64471 3.14471 8 3.94 8Z"/><path d="M7.5 8v3M12 8v4.5M16.5 8v3"/>',
    "save": '<path d="M3 6.4A2.4 2.4 0 0 1 5.4 4L17 4L21 8L21 18.6A2.4 2.4 0 0 1 18.6 21L5.4 21A2.4 2.4 0 0 1 3 18.6Z"/><path d="M8 4v5.5h7V4"/><path d="M7 21v-6h10v6"/>',
    "save-as": '<path d="M4 5.4A2.4 2.4 0 0 1 6.4 3L14 3L20 9L20 18.6A2.4 2.4 0 0 1 17.6 21L6.4 21A2.4 2.4 0 0 1 4 18.6Z"/><path d="M14 3v6h6"/><path d="M12 11v6M9.5 14l2.5 2.5L14.5 14"/>',
    "scroll": '<path d="M8.5 6.5L12 3 15.5 6.5"/><path d="M8.5 17.5L12 21 15.5 17.5"/><path d="M12 3v18"/>',
    "search": '<path d="M10.7 4.1C14.3451 4.1 17.3 7.05492 17.3 10.7C17.3 14.3451 14.3451 17.3 10.7 17.3C7.05492 17.3 4.1 14.3451 4.1 10.7C4.1 7.05492 7.05492 4.1 10.7 4.1Z"/><path d="M15.6 15.6l4.9 4.9"/>',
    "settings": '<path d="M3.5 7.5h10.5M18 7.5h2.5"/><path d="M3.5 16.5h3M10.5 16.5h10"/><path d="M16 5v5"/><path d="M8 14v5"/>',
    "split": '<path d="M3.5 12h6.5"/><path d="M10 12h4.5a4 4 0 0 0 4-4V4.6"/><path d="M10 12h4.5a4 4 0 0 1 4 4v3.4"/><path d="M15.6 7.6l3-3 3 3"/><path d="M15.6 16.4l3 3 3-3"/>',
    "stats": '<path d="M3 18l5.5-6.2 4 3.6L20.5 6"/><path d="M15.5 6h5v5"/>',
    "trash": '<path d="M3.5 6.5h17"/><path d="M9 6.5V3.5h6v3"/><path d="M6.15 8.65A2.16 2.16 0 0 1 8.16 6.5L15.84 6.5A2.16 2.16 0 0 1 17.85 8.65L17.15 18.85A2.16 2.16 0 0 1 14.84 21L9.16 21A2.16 2.16 0 0 1 6.85 18.85Z"/><path d="M10 11v6M14 11v6"/>',
    "undo": '<path d="M4 9h9.5a5.5 5.5 0 0 1 0 11H7.5"/><path d="M8 4.5L3.5 9 8 13.5"/>',
    "wrap": '<path d="M3.5 5.5h17M3.5 18.5h17"/><path d="M3.5 12h12a3.2 3.2 0 0 1 0 6.4h-2.2"/><path d="M11.2 16.2l-2 2.2 2 2.2"/>',
}


def paths() -> dict[str, str]:
    """全部图标的 ``<path>`` 数据（只读副本）。

    外部工具（如 ``tools/export_icons.py`` 导出可复用图标库）用它拿原始路径，
    不直接摸 ``_PATHS``，避免以后改名时外面的脚本静默拿到空表。
    """
    return dict(_PATHS)


def stroke_for(size: int) -> float:
    """笔宽：``max(1.4, 24 × 1.05 / size)`` —— 等效物理笔宽不低于 1.05px（§三.2）。

    18px 是公式的交叉点（25.2 / 18 = 1.4），所以 18px 及以上直接用素材标称值；
    16px 及以下要加粗，否则那条线在屏幕上会塌成一层浅灰。
    """
    return max(1.4, 24 * 1.05 / float(size))


def svg(name: str, color: str = Color.text, size: int = 20, stroke: float | None = None) -> str:
    """拼一个 24 栅格的 SVG；``width/height`` 给目标尺寸，缩放比由渲染器算（= size/24）。"""
    # 表里的实心块写的是 fill="currentColor"（素材原样），这里换成实际色值：
    # Qt 的 SVG 渲染器对 currentColor 支持不可靠，不能指望父级 color 生效。
    body = _PATHS.get(name, _PATHS["file"]).replace("currentColor", color)
    width = stroke_for(size) if stroke is None else stroke
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{width:g}" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )


def pixmap(name: str, color: str = Color.text, size: int = 20) -> QPixmap:
    """位图版（菜单、按钮用）。``scale=2`` 是超采样，不是尺寸：逻辑尺寸仍是 size。"""
    from PySide6.QtGui import QPainter
    from PySide6.QtCore import QRectF

    scale = 2
    renderer = QSvgRenderer(QByteArray(svg(name, color, size).encode("utf-8")))
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    pm.setDevicePixelRatio(float(scale))
    return pm


_ICON_CACHE: dict[tuple[str, str, int], QIcon] = {}


def icon(name: str, color: str = Color.text, size: int = 20) -> QIcon:
    key = (name, color, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    ic = QIcon(pixmap(name, color, size))
    _ICON_CACHE[key] = ic
    return ic


def accent_icon(name: str, size: int = 20) -> QIcon:
    return icon(name, ACCENT, size)


__all__ = ["icon", "pixmap", "accent_icon", "svg", "paths", "stroke_for"]
