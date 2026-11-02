"""图标路径一次性跑通（规范 §十 的要求）。

规范原话：「把所有 Geometry.Parse 过的路径串收集成一个测试工程跑一遍，
再断言每个 Icons.Get(name) 非 null。WPF 对 SVG 路径语法宽容但不完全一致，
错了不会抛异常，只是**图标静默消失**。」

Qt 的 QSvgRenderer 同理 —— 路径写错不会抛异常，只是渲染成空白。
所以这里逐个渲染图标，断言渲染结果**不是空白**。

除渲染之外还把《图标规范》§十一 的三道闸一并跑掉：

* 闸 1：程序表里的键 ⊆ 素材键集合（键名写错 = 静默画 ``file``）；
* 闸 2：表里没有没被引用的键（§八.2「不许留备用键」）；
* 闸 3：笔宽只有一处算（第二份 ``stroke-width`` 字面量就是违规）；
* 闸 4：调用点尺寸只落在 §三.4 的档位上（13/14/16/18/20/24/32）；
* 闸 5：缩放比 = size/24（渲染结果与素材 PNG 逐像素重合）。
素材不在时（只带源码分发）闸 1/2/5 自动跳过 —— 它们是素材闸，不是代码闸。
"""

from __future__ import annotations

import ast
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

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SVG_DIR = os.path.join(ROOT, "icons", "Unified", "svg")
PNG_DIR = os.path.join(ROOT, "icons", "Unified", "png")

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


def _py_files() -> list[str]:
    out = []
    for dirpath, _, files in os.walk(os.path.join(ROOT, "txtFormat", "app")
                                     if os.path.isdir(os.path.join(ROOT, "txtFormat", "app"))
                                     else os.path.join(ROOT, "app")):
        for fn in files:
            if fn.endswith(".py"):
                out.append(os.path.join(dirpath, fn))
    return out


def _string_consts(path: str) -> set[str]:
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except SyntaxError:
        return set()
    return {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def main() -> int:
    QApplication.instance() or QApplication([])   # QApplication 必须先建，QImage 才能用

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

    # ---- 闸 1：键全命中素材（§十一）
    asset_keys: set[str] = set()
    if os.path.isdir(SVG_DIR):
        asset_keys = {os.path.splitext(f)[0] for f in os.listdir(SVG_DIR) if f.endswith(".svg")}
        missing = sorted(set(names) - asset_keys)
        check("闸1-表里的键都在素材里", not missing, str(missing))

        # ---- 闸 2：没有备用键（每个键至少被一处字符串引用；字符串法宽松，只漏杀不误伤）
        referenced: set[str] = set()
        for path in _py_files():
            if path.endswith(os.path.join("ui", "icons.py")):
                continue
            referenced |= _string_consts(path) & set(names)
        unused = sorted(set(names) - referenced)
        check("闸2-没有未被引用的键", not unused, str(unused))

        # ---- 闸 6：程序引用的键 ⊆ 表（缺了会被 fallback 静默画成 file）。
        # 只扫 app/ui —— 图标引用只发生在界面层；app 根下 selftest.py 的
        # JSON 字段名 "detail" 恰与素材某键撞名，扫进去就是误伤。
        # 字符串交集仍会撞上 "error"（kind=）这类，但对应的键都在表里，
        # 所以这里报出来的只会是真缺失 —— 除下面这批与素材键撞名的
        # CSS/样式关键字（theme.py 的 font-style 值，程序不通过 icons API 用）：
        _GATE6_SKIP = {"italic"}
        ui_files = [p for p in _py_files() if os.sep + "ui" + os.sep in p
                    and not p.endswith(os.path.join("ui", "icons.py"))]
        wanted: set[str] = set()
        for path in ui_files:
            wanted |= _string_consts(path) & asset_keys
        absent = sorted(wanted - _GATE6_SKIP - set(names))
        check("闸6-引用的键都在表里", not absent, str(absent))

        # ---- 闸 5：缩放比 = size/24（渲染与素材 PNG 逐像素重合）
        sample = "folder"
        png_path = os.path.join(PNG_DIR, f"{sample}-24.png")
        if os.path.exists(png_path):
            want = QImage(png_path)
            svg = icons.svg(sample, "#1B1B1B", 24)
            got = QImage(24, 24, QImage.Format.Format_ARGB32)
            got.fill(Qt.GlobalColor.transparent)
            p = QPainter(got)
            QSvgRenderer(svg.encode("utf-8")).render(p, QRectF(0, 0, 24, 24))
            p.end()
            diff = sum(1 for y in range(24) for x in range(24)
                       if (want.pixelColor(x, y).alpha() > 128) != (got.pixelColor(x, y).alpha() > 128))
            # 容差给到 16：素材 PNG 是 Chrome 渲的、这里是 Qt，圆角边缘抗锯齿
            # 会差出 1px 摆动（整条轮廓 ~300 像素，5% 以内都算重合；
            # 真错缩放比时差异是整体错位，轻松破百）。
            check("闸5-缩放比是 size/24（与素材重合）", diff <= 16, f"不一致像素 {diff}")

    # ---- 闸 3：笔宽只有一处算（§十）
    for py in _py_files():
        text = open(py, encoding="utf-8").read()
        hits = [kw for kw in ("stroke-width", "25.2") if kw in text]
        if hits and not py.endswith(os.path.join("ui", "icons.py")):
            check("闸3-笔宽只在 icons.py 算", False, f"{os.path.basename(py)} 出现 {hits}")
    check("闸3-笔宽只在 icons.py 算", True)

    # ---- 闸 4：调用点尺寸只落在档位上（§三.4）
    allowed = set(icons.SIZES)
    for py in _py_files():
        try:
            tree = ast.parse(open(py, encoding="utf-8").read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("icon", "pixmap", "accent_icon")):
                continue
            size = None
            if len(node.args) >= 3 and isinstance(node.args[2], ast.Constant) \
                    and isinstance(node.args[2].value, int):
                size = node.args[2].value
            elif node.keywords:
                size = next((k.value.value for k in node.keywords
                             if k.arg == "size" and isinstance(k.value, ast.Constant)
                             and isinstance(k.value.value, int)), None)
            check(f"闸4-{os.path.basename(py)}:{node.lineno} 尺寸 {size} 在档位上",
                  size is None or size in allowed, str(size))

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
