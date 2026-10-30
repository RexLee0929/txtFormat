"""路径解析：兼容源码运行与 PyInstaller 打包后的运行环境。"""

from __future__ import annotations

import os
import sys


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def root_dir() -> str:
    """程序根目录（可执行文件所在目录 / 源码根目录）。"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def package_dir() -> str:
    """app 包所在目录（打包后为 _MEIPASS/app）。"""
    if is_frozen():
        return os.path.join(getattr(sys, "_MEIPASS", root_dir()), "app")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    return os.path.join(package_dir(), "data")


def asset(*parts: str) -> str:
    return os.path.join(package_dir(), "assets", *parts)


def user_config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "txtFormat")
    os.makedirs(path, exist_ok=True)
    return path


def find_user_file(filename: str) -> str | None:
    """按“程序目录 → 用户配置目录 → 当前目录”的顺序查找用户自定义文件。"""
    candidates = [
        os.path.join(root_dir(), filename),
        os.path.join(user_config_dir(), filename),
        os.path.join(os.getcwd(), filename),
        os.path.join(data_dir(), filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


__all__ = ["is_frozen", "root_dir", "package_dir", "data_dir", "asset",
           "user_config_dir", "find_user_file"]
