"""同步应用图标：brand/export/txtFormat → app/assets/。

图标的唯一来源是品牌管线（brand/svg → brand/export/<程序>/），本脚本只把
成品搬进程序，**不再在构建期用代码现画** —— 以前这里用 Qt 画的是旧版
图标，build.cmd 每次都跑它，会把新 logo 覆盖回旧图标（2026-11-01 实测踩过）。

调用方保持不变：build.cmd 与 write_cmd.py 生成的模板仍然执行
    python tools/make_icon.py
所以换源时只需要改这里，构建链不用动。

用法：
    python tools/make_icon.py [源目录]
源目录解析顺序：命令行参数 > 环境变量 BRAND_EXPORT_DIR >
相对仓库探测（../../brand/export/txtFormat）。
"""

from __future__ import annotations

import os
import shutil
import sys

#: 源目录里的文件名 → 程序 assets 里的文件名
FILES = {
    "txtFormat.ico": "app.ico",
    "txtFormat-256.png": "app.png",
}


def find_src() -> str:
    """按 命令行参数 > 环境变量 > 相对仓库探测 找品牌导出目录。"""
    if len(sys.argv) > 1:
        return sys.argv[1]
    env = os.environ.get("BRAND_EXPORT_DIR")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))      # txtFormat/tools
    root = os.path.dirname(here)                           # txtFormat/
    candidates = [
        os.path.join(root, os.pardir, "brand", "export", "txtFormat"),
        os.path.join(root, os.pardir, os.pardir, "brand", "export", "txtFormat"),
    ]
    for c in candidates:
        if os.path.isfile(os.path.join(c, "txtFormat.ico")):
            return os.path.normpath(c)
    raise SystemExit("[错误] 找不到 brand/export/txtFormat（可传参数或设 BRAND_EXPORT_DIR）")


def main() -> int:
    src_dir = find_src()
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "app", "assets")
    os.makedirs(out_dir, exist_ok=True)

    for src_name, dst_name in FILES.items():
        src = os.path.join(src_dir, src_name)
        if not os.path.isfile(src):
            raise SystemExit(f"[错误] 源文件不存在：{src}")
        dst = os.path.join(out_dir, dst_name)
        shutil.copyfile(src, dst)
        print(f"  {src_name} -> {dst}  ({os.path.getsize(dst)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
