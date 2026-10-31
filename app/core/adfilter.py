"""广告检查与“自定义替换/删除”。

流程与原程序一致：

1. “广告检查及字符串计数” —— 用当前表达式扫描全文，把命中的内容写入
   ``remove.txt``（供人工核对），同时生成 ``replace.txt``（旧→新对照）。
2. 人工编辑并保存 remove.txt。
3. “自定义替换/删除” —— 逐行读取 remove.txt，把文档中出现的这些内容删掉。

``replace.txt`` 支持两种写法：
    ``旧内容``                → 删除
    ``旧内容<TAB>新内容``      → 替换
"""

from __future__ import annotations

import os
import re

from . import encoding as enc
from . import regexlib


def scan(text: str, pattern: str, ignore_case: bool = False) -> list[str]:
    """返回所有命中的文本片段（按出现顺序、已去重）。"""
    rx = regexlib.compile_pattern(pattern, ignore_case)
    seen: set[str] = set()
    out: list[str] = []
    for m in rx.finditer(text):
        frag = m.group(0)
        if not frag.strip() or frag in seen:
            continue
        seen.add(frag)
        out.append(frag)
    return out


def write_remove_list(path: str, fragments: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(fragments))


def read_remove_list(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    raw = enc.read_text_any(path)
    if raw is None:
        return []
    return [line for line in raw.replace("\r\n", "\n").split("\n") if line.strip()]


def apply_remove_list(text: str, fragments: list[str]) -> tuple[str, int]:
    """删除文档中出现的每一行内容，返回 (新文本, 删除次数)。"""
    removed = 0
    # 长的先删，避免短串把长串切碎
    for frag in sorted({f for f in fragments if f.strip()}, key=len, reverse=True):
        if frag in text:
            n = text.count(frag)
            text = text.replace(frag, "")
            removed += n
    return text, removed


def read_replace_pairs(path: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in read_remove_list(path):
        if "\t" in line:
            old, new = line.split("\t", 1)
        elif "==>" in line:
            old, new = line.split("==>", 1)
        else:
            old, new = line, ""
        if old.strip():
            pairs.append((old, new))
    return pairs


def apply_replace_pairs(text: str, pairs: list[tuple[str, str]]) -> tuple[str, int]:
    count = 0
    for old, new in sorted(pairs, key=lambda p: -len(p[0])):
        if old and old in text:
            count += text.count(old)
            text = text.replace(old, new)
    return text, count


def default_remove_path(base_dir: str) -> str:
    return os.path.join(base_dir, "remove.txt")


def default_replace_path(base_dir: str) -> str:
    return os.path.join(base_dir, "replace.txt")


def classify(lines: list[str], pattern: str) -> list[str]:
    """把 remove.txt 中“明显不该删”的超长行标出来（供界面提醒）。"""
    out: list[str] = []
    for line in lines:
        if len(line) > 200 and not re.search(pattern, line):
            out.append(line)
    return out


__all__ = [
    "scan", "write_remove_list", "read_remove_list", "apply_remove_list",
    "read_replace_pairs", "apply_replace_pairs", "default_remove_path",
    "default_replace_path", "classify",
]
