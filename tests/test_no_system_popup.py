"""规范 §十 要求的**源码级断言**：全仓搜禁用模式必须零命中。

规范 §七 的三条硬禁止：
  * 系统消息框：``QMessageBox`` / ``MessageBox.Show`` / ``alert(`` 等
  * 提示音：``SystemSounds`` / ``MessageBeep`` / ``PlaySound``
  * 弹窗叠弹窗

「代码里看着没写」不等于「听不到」—— 框架的默认框会替你响。所以这条断言
写进测试里，改坏了立刻能发现。

只扫**源码目录**（app/ 与 installer/winforms/），排除构建产物与二进制。
"""

from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 要扫的目录（相对 ROOT）
SCAN_DIRS = ["app", "installer/winforms"]

#: 要跳过的目录名
SKIP_DIRS = {"__pycache__", "bin", "obj", ".git", ".venv", "build", "dist",
             "artifacts", ".sync-backup"}

#: 要跳过的文件名后缀（二进制）
SKIP_SUFFIX = (".pyc", ".exe", ".dll", ".pdb", ".ico", ".png", ".jpg",
               ".zip", ".json", ".pyz")

#: (标签, 正则) —— 正则只在 .py / .cs / .cmd / .spec 文件里找
BANNED = [
    # ---- §七 1. 系统消息框
    ("系统消息框 QMessageBox", re.compile(r"\bQMessageBox\b")),
    ("系统消息框 MessageBox.Show", re.compile(r"\bMessageBox\s*\.\s*Show\b")),
    ("系统消息框 Shell32 #120", re.compile(r"#120\b")),
    # ---- §七 1. 提示音
    ("提示音 SystemSounds", re.compile(r"\bSystemSounds\b")),
    ("提示音 MessageBeep", re.compile(r"\bMessageBeep\b")),
    ("提示音 PlaySound", re.compile(r"\bPlaySound\b")),
    ("提示音 MessageBoxIcon", re.compile(r"\bMessageBoxIcon\b")),
    # ---- §七 4. 未捕获异常
    ("未捕获异常裸奔", re.compile(r"sys\.excepthook\s*=")),
]

#: 允许出现的白名单（注释里提到、或明确豁免的行）
ALLOW = [
    # errlog.py 里要挂 excepthook —— 那是规范要求的「未捕获异常写 error.log」
    (r"app/core/errlog\.py", None),
]

TEXT_EXT = (".py", ".cs", ".cmd", ".spec", ".md")


def iter_files():
    for rel_dir in SCAN_DIRS:
        base = os.path.join(ROOT, rel_dir.replace("/", os.sep))
        if not os.path.isdir(base):
            continue
        for dp, dn, fn in os.walk(base):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            for name in fn:
                if name.endswith(SKIP_SUFFIX):
                    continue
                if not name.endswith(TEXT_EXT):
                    continue
                full = os.path.join(dp, name)
                rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
                yield full, rel


def main() -> int:
    hits = []
    for full, rel in iter_files():
        # 白名单：整个文件豁免
        if any(rel.startswith(p) for p, _ in ALLOW):
            continue
        try:
            text = open(full, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            # 纯注释行不算命中（说明性文字不算调用）
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            for label, pat in BANNED:
                if pat.search(line):
                    hits.append((rel, i, label, stripped[:100]))

    print(f"扫描目录：{', '.join(SCAN_DIRS)}")
    print(f"检查模式：{len(BANNED)} 条")
    print()

    if not hits:
        print("零命中 ✓ —— 没有系统消息框、没有提示音、异常已接管")
        return 0

    print(f"命中 {len(hits)} 处：")
    for rel, line_no, label, text in hits:
        print(f"  {rel}:{line_no}  [{label}]  {text}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
