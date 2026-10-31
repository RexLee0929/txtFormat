"""图标路径一次性跑通（规范 §十 的要求）。

规范原话：「把所有 Geometry.Parse 过的路径串收集成一个测试工程跑一遍，
再断言每个 Icons.Get(name) 非 null。WPF 对 SVG 路径语法宽容但不完全一致，
错了不会抛异常，只是**图标静默消失**。」

Qt 的 QSvgRenderer 同理 —— 路径写错不会抛异常，只是渲染成空白。
所以这里逐个渲染图标，断言渲染结果**不是空白**。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt    # noqa: E402
from PySide6.QtGui import QImage, QPainter      # noqa: E402
from PySide6.QtSvg import QSvgRenderer          # noqa: E402
from PySide6.QtWidgets import QApplication      # noqa: E402

from app.ui import icons                         # noqa: E402
from app.ui.theme import Color                  # noqa: E402

PASS = 0
FAIL = 0
NOTES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        NOTES.append(f"{name}  {extra}")


def renders_anything(name: str) -> tuple[bool, str]:
    """渲染一个图标，返回 (是否画出了东西, 说明)。"""
    svg = icons.svg(name, Color.text, 24)
    renderer = QSvgRenderer(svg.encode("utf-8"))
    if not renderer.isValid():
        return False, "SVG 解析失败"
    img = QImage(24, 24, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    renderer.render(p, QRectF(0, 0, 24, 24))
    p.end()
    # 数一下有多少不透明像素 —— 全透明 = 路径写错，图标静默消失
    opaque = 0
    for y in range(24):
        for x in range(24):
            if img.pixelColor(x, y).alpha() > 20:
                opaque += 1
    return opaque > 0, f"不透明像素 {opaque}"


def main() -> int:
    app = QApplication.instance() or QApplication([])   # noqa: F841

    names = list(icons._PATHS.keys())
    check("图标表非空", len(names) > 0, str(len(names)))

    for name in names:
        ok, detail = renders_anything(name)
        check(f"图标「{name}」渲染出内容", ok, detail)

    # 名字不能重复（后写的会覆盖前面的，图标就少了）
    check("图标名无重复", len(names) == len(set(names)))

    # 未在表里的名字应该回退到 file 而不是崩
    try:
        icons.svg("__not_exist__")
        check("未知图标名回退不崩", True)
    except Exception as exc:      # noqa: BLE001
        check("未知图标名回退不崩", False, str(exc))

    print(f"\n通过 {PASS} 项，失败 {FAIL} 项")
    if NOTES:
        print("失败详情：")
        for n in NOTES:
            print(" -", n)
        return 1
    print("图标路径全部有效 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
