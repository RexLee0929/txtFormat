"""版本与应用元信息。

**版本号只有一个来源**（规范 §一）：``installer/version.props``。
界面标题、关于框、exe 版本资源、安装器全部从这一处取 —— 改版本只改 props，
任何地方都不允许再手写字面量（历史问题：py 与 props 各一份，靠人记着同步）。

打包时 ``version.props`` 会随包进 exe（见 ``txtFormat.spec`` 的 datas），
所以运行期和开发期取的是同一份文件。
"""

from __future__ import annotations

import os
import re
import sys

APP_NAME = "txtFormat"          # 程序名：仅英文名
APP_TITLE = "txtFormat"
APP_SUBTITLE = "长文本整理工具"

#: 版本号的唯一来源文件（相对仓库根 / exe 目录）
VERSION_FILE = os.path.join("installer", "version.props")

#: 读不到 props 时的兜底值 —— 自检会断言「不是这个值」，缺文件能立刻发现
FALLBACK_VERSION = "0.0.0"

_VERSION_RX = re.compile(r"<Version>\s*([0-9]+(?:\.[0-9]+)*)\s*</Version>")


def _candidates() -> list[str]:
    """可能放着 version.props 的路径，按优先级排列。"""
    out: list[str] = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        out.append(os.path.join(base, "version.props"))
        out.append(os.path.join(base, VERSION_FILE))
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    out.append(os.path.join(here, VERSION_FILE))            # 仓库根：<root>/installer
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        out.append(os.path.join(exe_dir, "version.props"))
        out.append(os.path.join(exe_dir, VERSION_FILE))
    return out


def _read_version() -> str:
    for path in _candidates():
        try:
            with open(path, encoding="utf-8") as fh:
                found = _VERSION_RX.search(fh.read())
        except OSError:
            continue
        if found:
            return found.group(1)
    return FALLBACK_VERSION


APP_VERSION = _read_version()

#: 作者与联系方式（不设链接，界面内点击即复制到剪贴板）
AUTHOR = "Rex Lee"
AUTHOR_EMAIL = "rexlee@rexleepro.com"
COPYRIGHT = f"© 2026 {AUTHOR}"

__all__ = ["APP_NAME", "APP_VERSION", "APP_TITLE", "APP_SUBTITLE", "VERSION_FILE",
           "FALLBACK_VERSION", "AUTHOR", "AUTHOR_EMAIL", "COPYRIGHT"]
