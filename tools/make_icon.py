"""生成应用图标 assets/app.ico（多尺寸 PNG 容器，无第三方依赖）。"""

from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt      # noqa: E402
from PySide6.QtGui import (QColor, QFont, QImage, QLinearGradient,  # noqa: E402
                           QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QApplication                      # noqa: E402

from app.ui.theme import ACCENT, mix                            # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw(size: int) -> QImage:
    scale = 4
    img = QImage(size * scale, size * scale, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size * scale
    pad = s * 0.06
    radius = s * 0.22

    # 底板：强调色渐变
    grad = QLinearGradient(0, 0, s, s)
    grad.setColorAt(0.0, mix(ACCENT, "#FFFFFF", 0.28))
    grad.setColorAt(1.0, mix(ACCENT, "#000000", 0.10))
    path = QPainterPath()
    path.addRoundedRect(QRectF(pad, pad, s - 2 * pad, s - 2 * pad), radius, radius)
    p.fillPath(path, grad)

    # 纸页
    page = QPainterPath()
    m = s * 0.24
    w = s - 2 * m
    h = s - 2 * m
    page.addRoundedRect(QRectF(m, m + s * 0.02, w, h), s * 0.05, s * 0.05)
    p.fillPath(page, QColor("#FFFFFF"))

    # 文本行
    pen = QPen(QColor(mix(ACCENT, "#000000", 0.05)))
    pen.setWidthF(max(1.0, s * 0.028))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    for i, ratio in enumerate((0.30, 0.42, 0.54)):
        y = m + h * ratio
        x1 = m + w * 0.14
        x2 = m + w * (0.86 if i < 2 else 0.60)
        p.drawLine(int(x1), int(y), int(x2), int(y))

    # 对勾
    pen = QPen(QColor(mix(ACCENT, "#FFFFFF", 0.15)))
    pen.setWidthF(max(1.4, s * 0.075))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    cx, cy = m + w * 0.52, m + h * 0.75
    tick = QPainterPath()
    tick.moveTo(cx - w * 0.14, cy)
    tick.lineTo(cx - w * 0.03, cy + h * 0.10)
    tick.lineTo(cx + w * 0.20, cy - h * 0.12)
    p.drawPath(tick)
    p.end()

    return img.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)


def png_bytes(img: QImage) -> bytes:
    ba = QByteArray()                     # 必须持有引用，否则 QBuffer 悬空
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def write_ico(path: str) -> None:
    images = [draw(size) for size in SIZES]
    blobs = [png_bytes(img) for img in images]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for size, blob in zip(SIZES, blobs):
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32,
                               len(blob), offset)
        offset += len(blob)
    with open(path, "wb") as fh:
        fh.write(header + entries + b"".join(blobs))
    draw(256).save(os.path.splitext(path)[0] + ".png", "PNG")


def main() -> int:
    app = QApplication(sys.argv[:1])          # noqa: F841 - 需要 QGuiApplication 才能绘制
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "assets")
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, "app.ico")
    write_ico(target)
    print("written", target, os.path.getsize(target), "bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
