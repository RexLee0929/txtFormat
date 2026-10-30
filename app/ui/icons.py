"""内置 SVG 图标（Fluent 风格线性图标，不依赖任何图片资源）。"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import ACCENT, Color

_PATHS: dict[str, str] = {
    "new": '<path d="M6 3h7l5 5v13H6z"/><path d="M13 3v5h5"/>',
    "open": '<path d="M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
    "save": '<path d="M4 4h12l4 4v12H4z"/><path d="M8 4v6h7V4"/><path d="M8 20v-6h8v6"/>',
    "format": '<path d="M4 6h10"/><path d="M4 12h16"/><path d="M4 18h12"/>'
              '<circle cx="18" cy="6" r="2"/>',
    "check": '<circle cx="12" cy="12" r="8.5"/><path d="M8 12.5l2.6 2.6L16 9.5"/>',
    "clean": '<path d="M5 19h14"/><path d="M7 15l7-9 4 3-7 9z"/><path d="M10 18l-1.5 2"/>',
    "replace": '<path d="M4 8h11l-3-3"/><path d="M20 16H9l3 3"/>',
    "split": '<path d="M12 3v18"/><path d="M5 8l-2 4 2 4"/><path d="M19 8l2 4-2 4"/>',
    "merge": '<path d="M5 4v5c0 3 3 5 7 5s7 2 7 5v1"/><path d="M2 17l3 3 3-3"/>'
             '<path d="M19 4v3"/><path d="M5 4v3"/>',
    "goto": '<path d="M4 12h13"/><path d="M13 7l5 5-5 5"/><path d="M20 5v14"/>',
    "convert": '<path d="M4 9h13l-3-3"/><path d="M20 15H7l3 3"/>',
    "settings": '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h9M21 17h-1"/>'
                '<circle cx="15" cy="7" r="2"/><circle cx="9" cy="12" r="2"/>'
                '<circle cx="15" cy="17" r="2"/>',
    "undo": '<path d="M9 7L4 12l5 5"/><path d="M4 12h9a5 5 0 0 1 5 5v1"/>',
    "redo": '<path d="M15 7l5 5-5 5"/><path d="M20 12h-9a5 5 0 0 0-5 5v1"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    "next": '<path d="M5 12h12"/><path d="M13 7l5 5-5 5"/>',
    "prev": '<path d="M19 12H7"/><path d="M11 7l-5 5 5 5"/>',
    "folder": '<path d="M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
    "file": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v6"/><circle cx="12" cy="8" r="1"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v4h-4"/>',
    "read": '<path d="M4 5.5C6.5 4.5 9 4.5 12 6c3-1.5 5.5-1.5 8-.5v13c-2.5-1-5-1-8 .5-3-1.5-5.5-1.5-8-.5z"/>'
            '<path d="M12 6v13"/>',
    "list": '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4.5" cy="6" r="1"/>'
            '<circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
    "chart": '<path d="M4 20V4"/><path d="M4 20h16"/><path d="M8 17v-6M13 17V8M18 17v-3"/>',
    "link": '<path d="M10 14a4 4 0 0 1 0-5.6l2-2a4 4 0 0 1 5.6 5.6l-1 1"/>'
            '<path d="M14 10a4 4 0 0 1 0 5.6l-2 2a4 4 0 0 1-5.6-5.6l1-1"/>',
    "trash": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    "rename": '<path d="M4 20h16"/><path d="M6 16l9-9 3 3-9 9z"/>',
    "wrap": '<path d="M4 6h16"/><path d="M4 12h11a3 3 0 0 1 0 6h-3"/><path d="M14 15l-2 3 2 3"/>',
    "font": '<path d="M5 19L10 6h1l5 13"/><path d="M7.5 14h6"/>',
    "mail": '<rect x="3" y="5.5" width="18" height="13" rx="2"/>'
            '<path d="M3.6 7l7.3 5.2a2 2 0 0 0 2.2 0L20.4 7"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/>'
            '<path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3"/>',
    # ---- 菜单补全 ----
    "save-as": '<path d="M4 4h12l4 4v12H4z"/><path d="M8 4v6h7V4"/>'
               '<path d="M8 20v-6h8v6"/><path d="M17 12l4 4-4 4"/>',
    "insert": '<path d="M12 5v14"/><path d="M5 12h14"/>'
              '<path d="M4 3h4M16 3h4M4 21h4M16 21h4"/>',
    "indent": '<path d="M4 6h16"/><path d="M10 12h10"/><path d="M10 18h10"/>'
              '<path d="M4 10l2.5 2L4 14z"/>',
    "outdent": '<path d="M4 6h16"/><path d="M10 12h10"/><path d="M10 18h10"/>'
               '<path d="M6.5 10L4 12l2.5 2z"/>',
    "case": '<path d="M3 19L7.5 6h1L13 19"/><path d="M5 14h6"/>'
            '<path d="M15 12.5a3.5 3.5 0 1 1 0 7h-2v-7z"/><path d="M18.5 16a3.5 3.5 0 0 0-3.5-3.5"/>',
    "reopen": '<path d="M4 5a1 1 0 0 1 1-1h5l2 2h7a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"/>'
              '<path d="M12 10.5a3.5 3.5 0 1 1-1.6 6.6"/><path d="M12 8v3h-3"/>',
    "pin": '<path d="M12 17v5"/><path d="M8 3h8l-1 6 3 3v2H6v-2l3-3z"/>',
    "rulers": '<path d="M3 12h18"/><path d="M5 10v4M9 10v4M13 10v4M17 10v4M21 10v4"/>',
    "scroll": '<path d="M12 4v14"/><path d="M7 13l5 5 5-5"/><path d="M5 21h14"/>',
    "stats": '<path d="M4 20V4"/><path d="M4 20h16"/>'
             '<rect x="7" y="12" width="3" height="6"/><rect x="12" y="8" width="3" height="10"/>'
             '<rect x="17" y="14" width="3" height="4"/>',
}


def svg(name: str, color: str = Color.text, size: int = 20, stroke: float = 1.6) -> str:
    body = _PATHS.get(name, _PATHS["file"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )


def pixmap(name: str, color: str = Color.text, size: int = 20) -> QPixmap:
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


__all__ = ["icon", "pixmap", "accent_icon", "svg"]
