#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 PyInstaller 产物打成 payload.zip，供安装器内嵌。

    python tools/make_payload.py                 # 默认：artifacts/txtFormat → installer/winforms/payload.zip
    python tools/make_payload.py --src D:\\X --dst Y.zip

规则：
  * 只收需要的文件，运行期产生的个人文件（config.json / settings.json / custreg.txt / *.log）
    绝不进包，否则会把开发者本机的设置带给用户；config.json 本就不该在包里
    （规范 §三.2：不勾「覆盖现有配置」就天然不会碰它）。
  * 按解压后体积而不是压缩包体积报告，安装位置页显示的"所需磁盘空间"才对。
"""

from __future__ import annotations

import argparse
import sys
import time
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

#: 扩展名/文件名黑名单 —— 编译中间产物与本机运行时文件
SKIP_EXT = {".pdb", ".pyc", ".pyo", ".log"}
SKIP_NAMES = {"config.json", "settings.json", "custreg.txt", "desktop.ini", "thumbs.db"}


def wanted(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() in SKIP_EXT:
        return False
    if path.name.lower() in SKIP_NAMES:
        return False
    return True


def newest_source() -> tuple[float, str]:
    """程序本体源码里最新的修改时间（app/**/*.py + spec + requirements）。"""
    newest, who = 0.0, ""
    targets = [ROOT / "txtFormat.spec", ROOT / "requirements.txt"]
    app_dir = ROOT / "app"
    if app_dir.is_dir():
        targets.extend(app_dir.rglob("*.py"))
    for item in targets:
        if not item.is_file():
            continue
        mtime = item.stat().st_mtime
        if mtime > newest:
            newest, who = mtime, str(item.relative_to(ROOT))
    return newest, who


def build(src: Path, dst: Path, allow_stale: bool = False) -> int:
    if not src.is_dir():
        print(f"[错误] 找不到主程序产物目录：{src}")
        print("       请先运行 build.cmd（或 python -m PyInstaller txtFormat.spec）")
        return 1

    files = sorted(p for p in src.rglob("*") if wanted(p))
    if not files:
        print(f"[错误] {src} 下没有可打包的文件")
        return 1

    exe = src / "txtFormat.exe"
    if not exe.is_file():
        print(f"[错误] 缺少主程序：{exe}")
        return 1

    # 防呆：exe 比源码旧就说明没重新打包 —— 这一步以前是静默的，
    # 结果安装包里塞的是旧代码，界面上改过的 bug 一个都没生效（实打实踩过）。
    src_mtime, who = newest_source()
    exe_mtime = exe.stat().st_mtime
    if not allow_stale and src_mtime > exe_mtime + 0.5:
        print("[错误] 主程序产物比源码旧，安装包会带上旧代码：")
        print(f"       源码 {who} 改于 {time.strftime('%m-%d %H:%M', time.localtime(src_mtime))}")
        print(f"       {exe} 生成于 {time.strftime('%m-%d %H:%M', time.localtime(exe_mtime))}")
        print("       请先运行 build.cmd 重新打包程序本体，再生成安装包。")
        print("       （确认要用旧产物时加 --allow-stale）")
        return 1

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()

    raw = 0
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            # 用相对路径，安装器按目录结构还原
            z.write(p, str(p.relative_to(src)).replace("\\", "/"))
            raw += p.stat().st_size

    packed = dst.stat().st_size
    print(f"[完成] {dst}")
    print(f"       文件 {len(files)} 个")
    print(f"       解压后 {raw / 1048576:.1f} MB　压缩后 {packed / 1048576:.1f} MB"
          f"　压缩比 {100 * packed / max(raw, 1):.1f}%")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成安装器内嵌的 payload.zip")
    ap.add_argument("--src", default=str(ROOT / "artifacts" / "txtFormat"),
                    help="PyInstaller 产物目录（默认 artifacts/txtFormat）")
    ap.add_argument("--dst", default=str(ROOT / "installer" / "winforms" / "payload.zip"),
                    help="输出的 zip 路径")
    ap.add_argument("--allow-stale", action="store_true",
                    help="主程序产物比源码旧时仍继续（仅用于确认过的特殊场景）")
    args = ap.parse_args()
    return build(Path(args.src).resolve(), Path(args.dst).resolve(), args.allow_stale)


if __name__ == "__main__":
    raise SystemExit(main())