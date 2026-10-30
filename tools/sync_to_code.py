"""把编辑区内容同步到发布区（D:\\Code\\txtFormat），不做任何 git 操作。

按《分区规范》§四实现：**白名单是唯一实现**，硬编码在下面三组常量里。

    python tools/sync_to_code.py                 # 预演（默认）
    python tools/sync_to_code.py --apply         # 落盘
    python tools/sync_to_code.py --apply --prune # 同时删除发布区里多余的文件
    python tools/sync_to_code.py --dest D:\\Code\\txtFormat

要点：

* 编辑区只贡献白名单命中的文件（`SOURCE_FILES` + `SOURCE_DIRS`，再排掉
  `SKIP_PARTS` / `SKIP_NAMES` / `SKIP_SUFFIX` / 任何 `_` 开头的路径）。
* 发布区照实全收（只跳过 `.git` 与 `.sync-backup`），这样**越界内容**
  （产物目录、运行产物、别的会话塞进来的东西）才会出现在"多余"里，
  加 `--prune` 才能清掉。
* 新增一类文件要进发布区 → 加进 `SOURCE_FILES` / `SOURCE_DIRS` →
  先跑预演确认它出现在计划里，再 `--apply`。漏加的表现是
  **永远同步不过去，且不报错**。

产物不进发布区：安装包在编辑区 `artifacts/`，由工具区 `release.py` 直接
上传为 Release 资产。`--with-build` 已移除（与分区规范冲突）。
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DEST = r"D:\Code\txtFormat"

# ---------------------------------------------------------------- 白名单
#: 根目录下允许进发布区的文件（规范 §四「根文件」；按本工程实际结构定制）
SOURCE_FILES = {
    "README.md", "CHANGELOG.md", "DEVELOPMENT.md", "LICENSE", ".gitignore",
    "requirements.txt",
    "run.py", "run.cmd", "setup.cmd",
    "build.cmd", "build-installer.cmd",
    "txtFormat.spec",     # PyInstaller 打包配置
    "custreg.txt",        # 随程序一起装的自定义正则示例
}

#: 允许进发布区的目录（规范 §四「目录」；本工程为 app/installer/tools/tests + releases。
#: releases/ 放每个版本的 GitHub Release 正文 vX.Y.Z.md。
#: docs/ 不进发布区——截图与遗留资料只留在编辑区）
SOURCE_DIRS = ["app", "installer", "tools", "tests", "releases"]

#: 路径里出现这些片段就跳过（任何层级）—— 编译中间物、产物、同步记账
SKIP_PARTS = {"bin", "obj", ".vs", ".venv", "build", "dist", "artifacts",
              "__pycache__", ".pytest_cache", ".mypy_cache",
              ".idea", ".vscode", ".sync-backup", "_shots", ".git"}

#: 文件名前缀黑名单 —— 只挡真·临时物（截图 / 一次性探测脚本）。
#: 注意 **不能**用"任何 _ 开头"：`__init__.py` 是包标记文件，必须进仓库。
SKIP_PREFIX = ("_", "~$")

#: 文件名黑名单 —— 运行产物、构建中间物、同步工具的记账文件
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", "payload.zip",
              "config.json", "error.log", "selftest.json", "selftest-window.png",
              ".sync-state.json"}

#: 后缀黑名单 —— 中间物 / 日志 / 调试符号 / IDE 工程文件
SKIP_SUFFIX = (".pyc", ".pyo", ".log", ".cache", ".suo", ".user", ".pdb")

#: 发布区里要**保留**的顶层目录（本机记账 / 仓库，不属于同步内容）
PUB_KEEP_TOP = {".git", ".sync-backup"}


def _skip_name(name: str) -> bool:
    """真·临时物才挡：`_uitest_*.py` 这类；`__init__.py` 不挡。"""
    if name in SKIP_NAMES or name.lower().endswith(SKIP_SUFFIX):
        return True
    for pre in SKIP_PREFIX:
        if name.startswith(pre) and name != "__init__.py":
            return True
    return False


def collect_edit(base: str) -> dict[str, str]:
    """按白名单收集编辑区要同步的文件 → {相对路径: 绝对路径}。"""
    out: dict[str, str] = {}

    for name in sorted(SOURCE_FILES):                      # 根白名单文件
        full = os.path.join(base, name)
        if os.path.isfile(full):
            out[name] = full

    for sub in SOURCE_DIRS:                                # 白名单目录
        start = os.path.join(base, sub)
        if not os.path.isdir(start):
            continue
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = [d for d in dirnames
                           if d not in SKIP_PARTS and not d.startswith("_")]
            for name in filenames:
                if _skip_name(name):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, base).replace("\\", "/")
                out[rel] = full
    return out


def collect_pub(base: str) -> dict[str, str]:
    """照实收集发布区文件（只跳过 .git 与 .sync-backup），用于发现越界内容。"""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in PUB_KEEP_TOP]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, base).replace("\\", "/")
            out[rel] = full
    return out


def prune_empty_dirs(root: str) -> int:
    """删掉发布区里的空目录（prune 之后残留的目录壳）。"""
    removed = 0
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if os.path.abspath(dirpath) == os.path.abspath(root):
            continue
        if os.path.basename(dirpath) in PUB_KEEP_TOP:
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
                removed += 1
        except OSError:
            pass
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="同步编辑区到发布区（白名单制）")
    parser.add_argument("--dest", default=DEFAULT_DEST)
    parser.add_argument("--apply", action="store_true", help="真正写入（默认只预演）")
    parser.add_argument("--prune", action="store_true", help="删除发布区里多余的文件")
    args = parser.parse_args()

    if not os.path.isdir(args.dest):
        print(f"发布区不存在：{args.dest}")
        print("先手动创建该目录（或确认路径），再重新运行。")
        return 1

    src = collect_edit(ROOT)
    dst = collect_pub(args.dest)

    new = sorted(set(src) - set(dst))
    same, changed = [], []
    for rel in sorted(set(src) & set(dst)):
        if filecmp.cmp(src[rel], dst[rel], shallow=False):
            same.append(rel)
        else:
            changed.append(rel)
    extra = sorted(set(dst) - set(src))

    print(f"源（编辑区）：{ROOT}")
    print(f"目标（发布区）：{args.dest}")
    print(f"白名单命中 {len(src)} 个文件")
    print(f"新增 {len(new)}　更新 {len(changed)}　相同 {len(same)}"
          f"　发布区多余 {len(extra)}")
    for title, items in (("+ 新增", new), ("~ 更新", changed)):
        for rel in items:
            print(f"  {title}  {rel}")
    if extra:
        # 越界内容通常成片出现，按顶层目录归类显示，避免刷屏
        groups: dict[str, int] = {}
        for rel in extra:
            groups.setdefault(rel.split("/")[0], 0)
            groups[rel.split("/")[0]] += 1
        print("  发布区多余（发布区有、编辑区白名单里没有）：")
        for top, cnt in sorted(groups.items()):
            print(f"    - {top}/ …… {cnt} 个文件")
    if args.prune:
        if not extra:
            print("  没有要删除的文件。")
    elif extra:
        print("  （加 --prune 才会删除这些多余文件）")

    if not args.apply:
        print("\n预演结束，未写入任何文件。确认无误后加 --apply。")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(args.dest, ".sync-backup", stamp)
    for rel in changed:
        target = os.path.join(args.dest, rel)
        keep = os.path.join(backup, rel)
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        shutil.copy2(target, keep)

    for rel in new + changed:
        target = os.path.join(args.dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src[rel], target)

    removed = failed = 0
    if args.prune:
        for rel in extra:
            target = os.path.join(args.dest, rel)
            try:
                os.remove(target)
                removed += 1
            except OSError as exc:
                failed += 1
                print(f"  删除失败 {rel}: {exc}")
        prune_empty_dirs(args.dest)

    print(f"\n已写入 {len(new) + len(changed)} 个文件"
          + (f"，已删除 {removed} 个多余文件" if args.prune else "")
          + (f"，{failed} 个删除失败" if failed else "") + "。")
    if changed:
        print(f"被覆盖的旧文件已备份到：{backup}")
    print("git 操作请在你自己的发布工作空间里进行。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())