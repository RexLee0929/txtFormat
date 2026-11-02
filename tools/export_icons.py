# -*- coding: utf-8 -*-
"""把程序内置图标导出成可复用的图标库（SVG + PNG + 预览页）。

    .venv/Scripts/python.exe tools/export_icons.py [输出目录]

默认输出到工作区公共图标库的 **txtFormat 子目录**：``<工作区>/icons/txtFormat``。
那目录里还会有别的程序的图标 —— 本工具**只写自己那个子目录**，绝不触碰其它文件。

产物：

    svg/<name>.svg          24×24 线性图标，stroke 1.6、圆头圆角（与原程序一致）
    png/<name>-16|24|32|48  透明底 PNG，直接丢进别的程序用
    app-icon/txtFormat-*    程序图标各尺寸 + .ico
    icons.json              名称 → 中文含义 → 原始 path 数据（给其它技术栈解析）
    preview.html            自包含预览页（浅底/深底、四种尺寸）
"""

from __future__ import annotations

import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.ui import icons  # noqa: E402

#: 默认落点：工作区公共图标库里属于本程序的子目录（与 ClipSync / ComicConverter 并列）
DEFAULT_OUT = os.path.join(os.path.dirname(ROOT), "icons", "txtFormat")

#: 图标名 → 中文含义（预览页与 icons.json 用；换程序复用时看这个挑）
LABELS: dict[str, str] = {
    "new": "新建",
    "open": "打开",
    "save": "保存",
    "save-as": "另存为",
    "format": "格式整理",
    "check": "校验 / 通过",
    "clean": "清理 / 广告检查",
    "replace": "替换",
    "split": "分割 / 章节",
    "merge": "合并",
    "goto": "跳转",
    "convert": "转换",
    "settings": "设置 / 选项",
    "undo": "撤消 / 还原",
    "redo": "重做",
    "search": "查找",
    "next": "下一个",
    "prev": "上一个",
    "play": "运行",
    "folder": "文件夹",
    "file": "文件",
    "close": "关闭",
    "plus": "新增 / 添加",
    "info": "信息 / 关于",
    "error": "错误 / 危险",
    "refresh": "刷新 / 重载",
    "read": "阅读模式",
    "list": "列表 / 状态栏",
    "trash": "删除",
    "edit": "编辑 / 重命名",
    "wrap": "自动换行",
    "font": "字体",
    "mail": "邮件 / 邮箱",
    "copy": "复制",
    "insert": "插入",
    "indent": "缩进",
    "outdent": "反缩进",
    "case": "大小写",
    "pin": "置顶",
    "rulers": "标尺 / 水线",
    "scroll": "自动卷屏",
    "stats": "统计",
}

VIEWBOX = "0 0 24 24"
#: 出的是 24×24 的**素材**（不是某个尺寸的渲染结果），笔宽取 24px 档 = 素材标称 1.4。
#: 别在这里写第二个数字：换算只在 icons.stroke_for() 一处（《图标规范》§十一 闸 2）。
STROKE = icons.stroke_for(24)
COLOR = "#1B1B1B"          # 正文色；其它程序要别的颜色，替换 stroke 即可
PNG_SIZES = (16, 24, 32, 48)
APP_SIZES = (16, 24, 32, 48, 64, 128, 256)


def svg_text(name: str, color: str = COLOR) -> str:
    body = icons.paths()[name]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
            f'viewBox="{VIEWBOX}" fill="none" stroke="{color}" stroke-width="{STROKE}" '
            f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


def render_png(name: str, size: int, path: str) -> None:
    """用 QImage 画（不需要 QApplication，与 accent.py 同一手法）。"""
    from PySide6.QtCore import QByteArray, QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    scale = 2 if size <= 48 else 1        # 小图标 2× 超采样后缩回去，边缘更干净
    renderer = QSvgRenderer(QByteArray(svg_text(name).encode("utf-8")))
    img = QImage(size * scale, size * scale, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    if scale > 1:
        img = img.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    img.save(path, "PNG")


def write_preview(out_dir: str, names: list[str]) -> None:
    cards = []
    for name in names:
        label = LABELS.get(name, "")
        sizes = "".join(
            f'<span class="sz"><i style="width:{s}px;height:{s}px">{svg_text(name)}</i>'
            f'<em>{s}</em></span>' for s in (16, 24, 32, 48))
        cards.append(f"""
        <div class="card">
          <div class="big">{svg_text(name)}</div>
          <div class="meta"><b>{name}</b><span>{label}</span></div>
          <div class="sizes">{sizes}</div>
        </div>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>txtFormat 图标库</title>
<style>
  :root {{ --line:#E1E1E1; --text:#1B1B1B; --mute:#8A8A8A; --card:#FFFFFF; }}
  body {{ margin:0; padding:28px 32px 48px; background:#F3F3F3; color:var(--text);
         font:13px/1.5 "Microsoft YaHei UI","Segoe UI",sans-serif; }}
  h1 {{ font-size:19px; margin:0 0 4px; }}
  p.sub {{ color:#5C5C5C; margin:0 0 22px; font-size:12px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(168px,1fr)); gap:12px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:8px;
           padding:14px 14px 10px; text-align:center; }}
  .big svg {{ width:32px; height:32px; }}
  .meta {{ margin-top:8px; }}
  .meta b {{ display:block; font-size:12.5px; }}
  .meta span {{ color:var(--mute); font-size:11.5px; }}
  .sizes {{ display:flex; justify-content:center; align-items:flex-end; gap:10px;
            margin-top:10px; padding-top:8px; border-top:1px dashed var(--line); }}
  .sz {{ display:flex; flex-direction:column; align-items:center; gap:2px; }}
  .sz i {{ display:block; }}
  .sz i svg {{ width:100%; height:100%; }}
  .sz em {{ font-style:normal; color:#B5B5B5; font-size:10px; }}
  .dark {{ margin-top:26px; background:#1B1B1B; border-radius:8px; padding:18px 20px;
           color:#FFFFFF; }}
  .dark h2 {{ font-size:13px; margin:0 0 12px; font-weight:600; color:#E8E8E8; }}
  .dark .row {{ display:flex; flex-wrap:wrap; gap:18px; align-items:center; }}
  .dark .row svg {{ width:24px; height:24px; stroke:#FFFFFF; }}
</style></head><body>
<h1>txtFormat 图标库</h1>
<p class="sub">{len(names)} 个图标 · 24×24 viewBox · stroke {STROKE} · 圆头圆角 · 与程序内完全同源
（app/ui/icons.py）· 换色只需替换 stroke 属性</p>
<div class="grid">{''.join(cards)}</div>
<div class="dark"><h2>深色底（stroke 换成 #FFFFFF 直接可用）</h2>
<div class="row">{''.join(f'<span title="{n}">{svg_text(n, "#FFFFFF")}</span>' for n in names)}</div>
</div>
</body></html>"""
    with open(os.path.join(out_dir, "preview.html"), "w", encoding="utf-8") as fh:
        fh.write(html)


def main() -> int:
    out_dir = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    svg_dir = os.path.join(out_dir, "svg")
    png_dir = os.path.join(out_dir, "png")
    app_dir = os.path.join(out_dir, "app-icon")
    for d in (svg_dir, png_dir, app_dir):
        os.makedirs(d, exist_ok=True)

    data = icons.paths()
    names = sorted(data)
    for name in names:
        with open(os.path.join(svg_dir, f"{name}.svg"), "w", encoding="utf-8") as fh:
            fh.write(svg_text(name))
        for size in PNG_SIZES:
            render_png(name, size, os.path.join(png_dir, f"{name}-{size}.png"))

    # 程序图标（各尺寸 + ico），直接从品牌导出复制，保证与 exe 一致
    brand = os.path.join(os.path.dirname(ROOT), "brand", "export", "txtFormat")
    copied_app = 0
    if os.path.isdir(brand):
        for size in APP_SIZES:
            src = os.path.join(brand, f"txtFormat-{size}.png")
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(app_dir, f"txtFormat-{size}.png"))
                copied_app += 1
        ico = os.path.join(brand, "txtFormat.ico")
        if os.path.isfile(ico):
            shutil.copy2(ico, os.path.join(app_dir, "txtFormat.ico"))
            copied_app += 1

    meta = {
        "source": "txtFormat/app/ui/icons.py",
        "program": "txtFormat",
        "viewBox": VIEWBOX,
        "strokeWidth": STROKE,
        "strokeLinecap": "round",
        "strokeLinejoin": "round",
        "color": COLOR,
        "note": "路径数据为 24×24 viewBox；其它技术栈按 path 的 d 属性绘制即可，"
                "线宽 1.4、圆头圆角，颜色任意替换。",
        "sizes_png": list(PNG_SIZES),
        "icon_count": len(names),
        "icons": [{"name": n, "label": LABELS.get(n, ""), "paths": data[n]}
                  for n in names],
    }
    with open(os.path.join(out_dir, "icons.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)

    write_preview(out_dir, names)
    print(f"导出完成：{len(names)} 个图标 → {out_dir}")
    print(f"  svg/ {len(names)} 个，png/ {len(names) * len(PNG_SIZES)} 个，"
          f"app-icon/ {copied_app} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
