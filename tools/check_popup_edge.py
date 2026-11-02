"""按 popuptest.json 记录的弹层全局矩形，精确裁剪边缘并统计边框像素。

用法: check_popup_edge.py <out_dir> <key>
输出: <out_dir>/edge_<key>_bottom.png / _top.png / _corner.png
      + 四条边 1px 环上的颜色统计（判断边框有没有画出来）。
"""
import json
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

out_dir, key = sys.argv[1], sys.argv[2]
data = json.load(open(os.path.join(out_dir, "popuptest.json"), encoding="utf-8"))
info = data["popups"][key]
x, y, w, h = info["popup_rect"]
dpr = info["dpr"] or 1.0
img = QImage(os.path.join(out_dir, f"popup_{key}.png"))
px, py, pw, ph = round(x * dpr), round(y * dpr), round(w * dpr), round(h * dpr)
print(f"popup physical rect: {px},{py} {pw}x{ph}  dpr={dpr}  image={img.width()}x{img.height()}")

# 四条边外沿 0..3 px 的颜色采样（看是否有一条连续的浅灰边框线）
def scan_edge(name, pts):
    from collections import Counter
    cnt = Counter()
    for (sx, sy) in pts:
        c = img.pixelColor(sx, sy)
        cnt[(c.red(), c.green(), c.blue())] += 1
    print(name, "top colors:", cnt.most_common(4))

inset = 2
scan_edge("bottom rows:", [(sx, py + ph - 1 - o) for o in range(8)
                           for sx in range(px + inset, px + pw - inset, 3)])
scan_edge("top rows:   ", [(sx, py + o) for o in range(8)
                           for sx in range(px + inset, px + pw - inset, 3)])
scan_edge("left cols:  ", [(px + o, sy) for o in range(8)
                           for sy in range(py + inset, py + ph - inset, 3)])
scan_edge("right cols: ", [(px + pw - 1 - o, sy) for o in range(8)
                           for sy in range(py + inset, py + ph - inset, 3)])

# 弹层外部一圈（判断有没有 DWM 投影）
scan_edge("below shadow:", [(sx, py + ph + o) for o in range(1, 8)
                            for sx in range(px + inset, px + pw - inset, 2)])

def crop(name, x0, y0, cw, ch, sc=7):
    band = img.copy(max(0, x0), max(0, y0), cw, ch)
    band = band.scaled(cw * sc, ch * sc,
                       Qt.AspectRatioMode.IgnoreAspectRatio,
                       Qt.TransformationMode.FastTransformation)
    path = os.path.join(out_dir, name)
    band.save(path)
    print("saved", path)

crop(f"edge_{key}_bottom.png", px - 8, py + ph - 16, pw + 16, 30)
crop(f"edge_{key}_top.png", px - 8, py - 14, pw + 16, 30)
crop(f"edge_{key}_full.png", px - 6, py - 6, pw + 12, ph + 12, 3)
