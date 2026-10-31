"""由**程序图标**派生强调色（程序本体设计规范 §三）。

规范的原话：「唯一品牌色输入 = 程序图标。按钮底色、勾选标记、链接、选中胶囊、
输入框聚焦边、进度条，全部由图标主色算出来；代码里不允许出现品牌色字面值
（中性灰阶除外）。换图标整套界面跟着换。」

取主色的算法与安装器 ``Theme.cs`` 同源（两边必须一致，否则程序与安装器配色会分家）：

1. 把 app.ico 渲染成 64×64（保留 alpha），逐像素统计，先剔除
   ``A < 200``（半透明毛边）、``L > 0.92`` 或 ``L < 0.12``（近白近黑）、
   ``S < 0.18``（灰阶）；
2. 剩下的按 ``H/10°``、``S/0.1``、``L/0.1`` 三维分桶计数，取最高桶并合并相邻桶
   做加权平均，得到色相 ``H`` 与饱和度 ``S``（**不用图标的 L**）；
3. ``L`` 由规则统一给，四个用途色从同一个 ``(H, S)`` 推。

取不到主色时退回固定种子，和正常路径走同一套派生函数，
避免"兜底色"与"图标色"算出两套略有差异的值。
"""

from __future__ import annotations

import colorsys
import os

#: 取不到主色时的固定种子（色相 165°、饱和度 0.68）
FALLBACK_H = 165.0 / 360.0
FALLBACK_S = 0.68

#: **图标设计种子** —— 画图标时用的品牌色。
#:
#: 图标是整套配色的唯一输入（规范 §三），所以画图标不能反过来用界面强调色，
#: 否则就成了「图标由强调色生成、强调色又由图标派生」的循环。
#: 这个种子只描述「这个图标长什么样」，界面色一律从**渲染出来的图标**里取。
ICON_SEED_H = 34.0 / 360.0
ICON_SEED_S = 0.91


def _icon_path() -> str | None:
    """程序图标的路径（打包后是 sys._MEIPASS 里的临时目录）。"""
    import sys

    base = getattr(sys, "_MEIPASS", None)
    roots = []
    if base:
        roots.append(os.path.join(base, "app", "assets"))
        roots.append(os.path.join(base, "assets"))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    roots.append(os.path.join(here, "app", "assets"))
    roots.append(os.path.join(here, "assets"))
    for r in roots:
        p = os.path.join(r, "app.ico")
        if os.path.isfile(p):
            return p
    return None


def _hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    """(R, G, B) → (H 0..1, S 0..1, L 0..1)。"""
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    return h, s, l


def _from_hsl(h: float, s: float, l: float) -> str:
    """(H 0..1, S 0..1, L 0..1) → '#RRGGBB'。"""
    h = h - int(h // 1)
    s = min(max(s, 0.0), 1.0)
    l = min(max(l, 0.0), 1.0)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


# --------------------------------------------------------------- 取像素
def _ico_pixels(path: str) -> list[tuple[int, int, int, int]] | None:
    """读 .ico 里最大那张图，缩放到 64×64，返回 [(r, g, b, a), ...]。

    用 Qt 的 ICO 插件读（BMP/PNG 容器、隔行、16 位色、调色板等变体全覆盖）。
    以前是自己解 PNG：只认 8 位非隔行，换一个图标就静默退回兜底色，而且多出
    ~170 行容易出错的滤波代码。

    *为什么能用 Qt*：``QImage`` 不需要 ``QGuiApplication``（只有 ``QPixmap`` 需要，
    没有 GUI 应用时它会直接 abort 进程）。这里实测过：模块 import 期读 app.ico
    正常，所以 :data:`app.ui.theme` 里 ``_PALETTE = palette()`` 这种 import 期
    求值不受影响。

    缩放到 64×64 与安装器 ``Theme.cs`` 的 ``DrawImage(64×64)`` 对齐，
    保证程序与安装器算出的强调色一致。
    """
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage, QImageReader
    except ImportError:                     # 无 PySide6 时退回兜底种子
        return None

    reader = QImageReader(path)
    if not reader.canRead():
        return None

    # ICO 内含多张不同尺寸；挑面积最大的那张（信息量最全）
    best_index, best_area = -1, 0
    for i in range(max(1, reader.imageCount())):
        if not reader.jumpToImage(i):
            continue
        size = reader.size()
        area = size.width() * size.height()
        if area > best_area:
            best_index, best_area = i, area
    if best_index < 0 or not reader.jumpToImage(best_index):
        return None

    img = reader.read()
    if img.isNull():
        return None
    if img.width() != 64 or img.height() != 64:
        img = img.scaled(64, 64, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    img = img.convertToFormat(QImage.Format.Format_ARGB32)

    out: list[tuple[int, int, int, int]] = []
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            out.append((c.red(), c.green(), c.blue(), c.alpha()))
    return out


def icon_seed() -> tuple[float, float]:
    """图标主色的 (H, S)。取不到就退回固定种子。"""
    path = _icon_path()
    if not path:
        return FALLBACK_H, FALLBACK_S
    px = _ico_pixels(path)
    if not px:
        return FALLBACK_H, FALLBACK_S
    seed = _seed_from_pixels(px)
    if seed is None:
        return FALLBACK_H, FALLBACK_S
    h, s = seed
    # 灰调图标也要有颜色：饱和度太低时抬到 0.35
    # （与安装器 Theme.Apply 的同一条规则，两边必须一致）
    return h, max(s, 0.35)


def _seed_from_pixels(px: list[tuple[int, int, int, int]]) -> tuple[float, float] | None:
    """从像素列表取主色，返回 (H, S)；取不到返回 None。"""
    hist: dict[int, list[float]] = {}   # key → [n, sumH, sumS]
    valid = 0

    for r, g, b, a in px:
        if a < 200:                        # 半透明毛边
            continue
        h, s, l = _hsl(r, g, b)
        if l > 0.92 or l < 0.12:           # 近白、近黑
            continue
        if s < 0.18:                       # 灰阶
            continue
        key = (int(h * 36) << 16) | (int(s * 10) << 8) | int(l * 10)
        bk = hist.get(key)
        if bk is None:
            bk = [0.0, 0.0, 0.0]
            hist[key] = bk
        bk[0] += 1
        bk[1] += h
        bk[2] += s
        valid += 1

    if not hist or valid == 0:
        return None

    best_key = max(hist, key=lambda k: hist[k][0])
    if hist[best_key][0] / valid < 0.08:
        return None                       # 颜色太分散，当作没有主色

    # 相邻桶一起加权；用桶内真实 H/S 求和再平均，不要用桶中心值
    bh = best_key >> 16
    bs = (best_key >> 8) & 0xFF
    wsum = hsum = ssum = 0.0
    for key, (n, sh, ss) in hist.items():
        hh = key >> 16
        s_bucket = (key >> 8) & 0xFF
        if abs(hh - bh) > 1 or abs(s_bucket - bs) > 1:
            continue
        wsum += n
        hsum += sh
        ssum += ss

    if wsum <= 0:
        return None
    return hsum / wsum, ssum / wsum


def derive(h: float, s: float) -> dict[str, str]:
    """由 (H, S) 派生四个用途色（规范 §三 的公式表）。

    | 用途 | 公式 |
    |---|---|
    | 强调色 | ``HSL(H, min(S·1.05, .95), .245)`` |
    | 强调暗 | ``HSL(H, min(S·1.10, .95), .175)`` |
    | 浅底 | ``HSL(H, .32, .93)`` |
    | 微光悬停 | ``HSL(H, .28, .96)`` |
    """
    accent = _from_hsl(h, min(s * 1.05, 0.95), 0.245)
    dark = _from_hsl(h, min(s * 1.10, 0.95), 0.175)
    soft = _from_hsl(h, 0.32, 0.93)
    hover = _from_hsl(h, 0.28, 0.96)
    return {"accent": accent, "dark": dark, "soft": soft, "hover": hover}


def palette() -> dict[str, str]:
    """整套派生色。图标取不到时也走同一套函数，只是输入是固定种子。

    读图用 ``QImage``（不需要 QGuiApplication），所以 import 期即可安全求值；
    ``app.ui.theme`` 的模块级 ``_PALETTE = palette()`` 依赖这一点。
    """
    h, s = icon_seed()
    return derive(h, s)


__all__ = ["icon_seed", "derive", "palette", "FALLBACK_H", "FALLBACK_S"]
