"""章节解析、规范化、重排与分割。

原程序的“文件分割 / 章节整理”对话框在这里实现为可复用逻辑：
* ``CHAPTER_FORMATS`` —— 章节名正则预设（下拉框内容）
* :func:`parse_chapters` —— 解析章节列表（标题 / 起止行 / 字数 / 顺序）
* :func:`normalize_titles` —— 章节号中文 ↔ 阿拉伯数字规范化
* :func:`renumber` —— 重排章节顺序后重新编号
* :func:`split_by_chapters` / :func:`split_by_size` —— 分割
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .numcn import int_to_cn, mixed_to_int

CN_NUM = "壹贰叁肆伍陆柒捌玖一二两三四五六七八九十○〇零百千O0-9０-９"
CN_NUM_NARROW = "一三四五六七八九十○〇零百千O0-9０-９"

#: (下拉框显示名, 正则)
CHAPTER_FORMATS: list[tuple[str, str]] = [
    ("系统默认",
     r"(?:^|(?<=[ 　\t\n]))(?:正文 )?第[―－\-─—" + CN_NUM + r"]{1,12}[章节節回集卷部篇][^\n]{0,60}"),
    ("第 999 章 XXXX",
     r"(?:^|(?<=[ 　\t\n]))(?:正文 )?第[―－\-─—" + CN_NUM + r"]{1,7}(?:[章节回集卷部篇])[^\n]{0,80}"),
    ("第 999 卷 XXXX 第 999 章 XXXX",
     r"(?:^|(?<=[ 　\t\n]))(?:正文 )?第[―－\-─—" + CN_NUM + r"]{1,7}[章节節回集卷部篇][^\n]{0,80}"),
    ("☆、XXXX",
     r"(?<=[ 　\t\n])☆、[^\n]{1,40}"),
    ("1、XXXX",
     r"(?<=[ 　\t\n])(?:正文 )?[O0-9０-９]{1,6}、[^\n]{1,40}"),
    ("一、XXXX",
     r"(?<=[ 　\t\n])(?:正文 )?[" + CN_NUM_NARROW + r"]{1,7}、[^\n]{1,40}"),
    ("一 XXXX 或 1 XXXX",
     r"(?<=[ 　\t\n])(?:正文 )?[" + CN_NUM + r"]{1,7}[ 　\t][^\n]{1,40}"),
    ("一 或 1",
     r"(?<=[ 　\t\n])(?:正文 )?[" + CN_NUM + r"]{1,7}[ 　\t]*$"),
    ("XXXX (一 或 1)",
     r"(?<=[ 　\t\n])(?:正文 )?[^\n]{1,40}?[（(]\s*[" + CN_NUM_NARROW + r"]{1,7}\s*[）)]"),
    ("纯中文章节名",
     r"(?<=[ 　\t\n])[\x4e00-\u9fa5（）\(\)\[\]0-9 　\t]{2,30}$"),
]

DEFAULT_FORMAT = CHAPTER_FORMATS[0][1]

#: 从标题中提取“第 X 章”的数字部分
_TITLE_NUMBER = re.compile(
    r"(第[―－\-─—]?)([" + CN_NUM + r"]{1,12})([章节節回集卷部篇])"
)


@dataclass
class Chapter:
    index: int                 # 顺序号（从 1 开始）
    title: str                 # 章节标题（不含首尾空白）
    start: int                 # 标题在文本中的起始下标
    end: int = 0               # 章节正文结束下标（不含）
    char_count: int = 0        # 正文（含标题）字数
    number: int | None = None  # 解析出的章号
    suspect: bool = False      # 章号不连续时为 True

    @property
    def order_text(self) -> str:
        return f"{self.index}{'???' if self.suspect else ''}"


def _parse_number(title: str) -> int | None:
    m = _TITLE_NUMBER.search(title)
    if m:
        return mixed_to_int(m.group(2))
    m = re.search(r"([0-9０-９]+)", title)
    if m:
        return mixed_to_int(m.group(1))
    return None


def parse_chapters(text: str, pattern: str = DEFAULT_FORMAT) -> list[Chapter]:
    """按给定正则找出所有章节标题，并算出每章的范围与字数。"""
    try:
        rx = re.compile(pattern, re.MULTILINE)
    except re.error:
        return []
    hits = [(m.start(), m.group(0)) for m in rx.finditer(text) if m.group(0).strip()]
    chapters: list[Chapter] = []
    for i, (start, raw) in enumerate(hits):
        title = raw.strip()
        end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        number = _parse_number(title)
        chapters.append(Chapter(i + 1, title, start, end, end - start, number))
    # 标记章号不连续的项
    prev: int | None = None
    for ch in chapters:
        if ch.number is not None and prev is not None and ch.number != prev + 1:
            ch.suspect = True
        if ch.number is not None:
            prev = ch.number
    return chapters


def parse_chapters_from_lines(lines: list[str], pattern: str = DEFAULT_FORMAT) -> list[Chapter]:
    return parse_chapters("\n".join(lines), pattern)


# ------------------------------------------------------------------ 规范化
def normalize_titles(text: str, pattern: str, mode: str = "cn") -> tuple[str, int]:
    """把章节号统一成中文（cn）或阿拉伯数字（num）。返回 (新文本, 修改数)。"""
    try:
        rx = re.compile(pattern, re.MULTILINE)
    except re.error:
        return text, 0
    count = 0

    def fix_title(title: str) -> str:
        nonlocal count
        m = _TITLE_NUMBER.search(title)
        if not m:
            return title
        number = mixed_to_int(m.group(2))
        if number is None:
            return title
        if mode == "cn":
            new_num = int_to_cn(number)
        else:
            new_num = str(number)
        if new_num == m.group(2):
            return title
        count += 1
        return title[:m.start(2)] + new_num + title[m.end(2):]

    def repl(m: re.Match[str]) -> str:
        return fix_title(m.group(0))

    new_text = rx.sub(repl, text)
    return new_text, count


def renumber(text: str, pattern: str, mode: str = "cn", start: int = 1) -> tuple[str, int]:
    """按列表中出现的顺序重新编号（“重排章节顺序” / “按章节排版”）。"""
    try:
        rx = re.compile(pattern, re.MULTILINE)
    except re.error:
        return text, 0
    counter = start - 1
    changed = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal counter, changed
        title = m.group(0)
        mt = _TITLE_NUMBER.search(title)
        counter += 1
        if not mt:
            return title
        new_num = int_to_cn(counter) if mode == "cn" else str(counter)
        if new_num != mt.group(2):
            changed += 1
        unit = mt.group(3)
        return title[:mt.start(2)] + new_num + unit + title[mt.end(3):]

    new_text = rx.sub(repl, text)
    return new_text, changed


def make_chapter_title(index: int, title: str, mode: str = "cn") -> str:
    num = int_to_cn(index) if mode == "cn" else str(index)
    body = title.strip()
    if _TITLE_NUMBER.search(body):
        return body
    return f"第{num}章 {body}" if body else f"第{num}章"


# ------------------------------------------------------------------ 分割
def split_by_chapters(text: str, pattern: str = DEFAULT_FORMAT) -> list[tuple[str, str]]:
    """返回 [(章节标题, 章节内容)]，标题之前的内容归入“前言”。"""
    chapters = parse_chapters(text, pattern)
    if not chapters:
        return []
    out: list[tuple[str, str]] = []
    if chapters[0].start > 0:
        preface = text[: chapters[0].start].strip()
        if preface:
            out.append(("前言", preface))
    for ch in chapters:
        out.append((ch.title, text[ch.start:ch.end].rstrip()))
    return out


def safe_filename(name: str, fallback: str = "chapter") -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip(" .")
    return name[:120] or fallback


def unique_path(directory: str, stem: str, ext: str = ".txt") -> str:
    path = os.path.join(directory, stem + ext)
    if not os.path.exists(path):
        return path
    i = 2
    while True:
        path = os.path.join(directory, f"{stem}({i}){ext}")
        if not os.path.exists(path):
            return path
        i += 1


__all__ = [
    "CHAPTER_FORMATS", "DEFAULT_FORMAT", "Chapter", "parse_chapters",
    "normalize_titles", "renumber", "make_chapter_title", "split_by_chapters",
    "safe_filename", "unique_path",
]
