"""正则表达式引擎封装。

职责：
* 把原程序的 ``\\r\\n`` 表达式归一化为内部统一使用的 ``\\n`` 文本上可用；
* 兼容原程序的 ``$1`` 反引用写法；
* 提供查找、计数、替换、批量替换；
* 加载 ``custreg.txt``（自定义正则）与 ``custerr.txt``（自定义错别字）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .paths import find_user_file, root_dir
from .regexlib_data import BUILTIN, SEMI_CUSTOM, RegexEntry


# ------------------------------------------------------------------ 归一化
def normalize_pattern(pattern: str) -> str:
    """把针对 CRLF 文档书写的表达式改写成针对 LF 文档可用。"""
    if not pattern:
        return pattern
    return pattern.replace(r"\r\n", r"\n").replace("\r\n", "\n")


def convert_replacement(repl: str) -> str:
    """``$1`` / ``$&`` → Python 的 ``\\1`` / ``\\g<0>``。"""
    if not repl:
        return ""
    out: list[str] = []
    i = 0
    n = len(repl)
    while i < n:
        ch = repl[i]
        if ch == "\\" and i + 1 < n:
            out.append(repl[i:i + 2])       # 保留原有转义
            i += 2
            continue
        if ch == "$" and i + 1 < n:
            nxt = repl[i + 1]
            if nxt.isdigit():
                j = i + 1
                while j < n and repl[j].isdigit():
                    j += 1
                out.append("\\g<" + repl[i + 1:j] + ">")
                i = j
                continue
            if nxt in "&{":
                if nxt == "&":
                    out.append("\\g<0>")
                    i += 2
                    continue
                end = repl.find("}", i)
                if end > 0:
                    out.append("\\g<" + repl[i + 2:end] + ">")
                    i = end + 1
                    continue
        out.append(ch)
        i += 1
    return "".join(out)


# ------------------------------------------------------------------ 条目
@dataclass(slots=True)
class Entry:
    name: str
    pattern: str
    replacement: str = ""
    kind: str = "regex"
    checker: str = ""
    note: str = ""
    source: str = "内置"

    _compiled: re.Pattern[str] | None = field(default=None, repr=False)

    @property
    def regex(self) -> re.Pattern[str]:
        if self._compiled is None:
            self._compiled = compile_pattern(self.pattern)
        return self._compiled

    @property
    def is_checker(self) -> bool:
        return self.kind == "checker"

    @property
    def is_converter(self) -> bool:
        return self.kind == "converter"


_CACHE: dict[str, re.Pattern[str]] = {}


def compile_pattern(pattern: str, ignore_case: bool = False) -> re.Pattern[str]:
    key = ("i:" if ignore_case else "m:") + pattern
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    flags = re.MULTILINE
    if ignore_case:
        flags |= re.IGNORECASE
    compiled = re.compile(normalize_pattern(pattern), flags)
    if len(_CACHE) < 4000:
        _CACHE[key] = compiled
    return compiled


# ------------------------------------------------------------------ 库
class RegexLibrary:
    """内置 + 半自定义 + 用户自定义 的表达式集合。"""

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = base_dir or root_dir()
        self.entries: list[Entry] = []
        self.reload()

    # -------------------------------------------------------------- 加载
    def reload(self) -> None:
        self.entries = [Entry(**_as_dict(e)) for e in BUILTIN]
        self.entries += [Entry(**_as_dict(e)) for e in SEMI_CUSTOM]
        self.entries += self._load_custreg()
        self.entries += self._load_custerr()

    def _data_path(self, filename: str) -> str:
        found = find_user_file(filename)
        return found or os.path.join(self.base_dir, filename)

    def _load_custreg(self) -> list[Entry]:
        path = self._data_path("custreg.txt")
        out: list[Entry] = []
        for name, pattern, repl in _read_triples(path):
            out.append(Entry(name, pattern, repl, source="自定义"))
        return out

    def _load_custerr(self) -> list[Entry]:
        path = self._data_path("custerr.txt")
        triples = _read_triples(path)
        if not triples:
            return []
        pattern = "|".join(p for _, p, _ in triples if p)
        return [Entry("查找 常见错别字(自定义)", pattern, "", source="自定义")]

    # -------------------------------------------------------------- 查询
    def names(self) -> list[str]:
        return [e.name for e in self.entries]

    def get(self, name: str) -> Entry | None:
        for e in self.entries:
            if e.name == name:
                return e
        return None

    def index_of(self, name: str) -> int:
        for i, e in enumerate(self.entries):
            if e.name == name:
                return i
        return -1


def _as_dict(entry) -> dict:
    if isinstance(entry, RegexEntry):
        return entry._asdict()
    if isinstance(entry, dict):
        return entry
    return dict(zip(("name", "pattern", "replacement", "kind", "checker", "note"), entry))


def _read_triples(path: str) -> list[tuple[str, str, str]]:
    """读取“说明 / 表达式 / 替换”三行一组的自定义正则文件。"""
    if not os.path.exists(path):
        return []
    for codec in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            with open(path, "r", encoding=codec) as fh:
                raw = fh.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        return []
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[tuple[str, str, str]] = []
    i = 0
    while i + 1 < len(lines):
        name = lines[i].strip()
        if not name:
            i += 1
            continue
        pattern = lines[i + 1]
        repl = lines[i + 2] if i + 2 < len(lines) else ""
        if not pattern.strip():
            i += 1
            continue
        try:
            compile_pattern(pattern)
        except re.error:
            i += 1
            continue
        out.append((name, pattern, repl))
        i += 3
    return out


# ------------------------------------------------------------------ 操作
@dataclass(slots=True)
class Match:
    start: int
    end: int
    text: str


def find_all(text: str, pattern: str, ignore_case: bool = False, limit: int = 0) -> list[Match]:
    rx = compile_pattern(pattern, ignore_case)
    out: list[Match] = []
    for m in rx.finditer(text):
        out.append(Match(m.start(), m.end(), m.group(0)))
        if limit and len(out) >= limit:
            break
    return out


def count_matches(text: str, pattern: str, ignore_case: bool = False) -> tuple[int, int]:
    """返回 (匹配次数, 不同内容种类数)。"""
    rx = compile_pattern(pattern, ignore_case)
    seen: set[str] = set()
    total = 0
    for m in rx.finditer(text):
        total += 1
        seen.add(m.group(0))
    return total, len(seen)


def replace_all(text: str, pattern: str, replacement: str,
                ignore_case: bool = False, start: int = 0, end: int | None = None) -> tuple[str, int]:
    """替换全部（可限定区间），返回 (新文本, 替换次数)。"""
    rx = compile_pattern(pattern, ignore_case)
    if end is None:
        seg = text[start:]
        new_seg, n = rx.subn(convert_replacement(replacement), seg)
        return text[:start] + new_seg, n
    head, seg, tail = text[:start], text[start:end], text[end:]
    new_seg, n = rx.subn(convert_replacement(replacement), seg)
    return head + new_seg + tail, n


def collect_matches(text: str, pattern: str, ignore_case: bool = False,
                    template: str = "$0") -> list[str]:
    """按模板渲染每一处匹配（用于生成 remove.txt / replace.txt）。"""
    rx = compile_pattern(pattern, ignore_case)
    repl = convert_replacement(template)
    out: list[str] = []
    for m in rx.finditer(text):
        try:
            out.append(m.expand(repl))
        except re.error:
            out.append(m.group(0))
    return out


def is_valid(pattern: str) -> bool:
    try:
        compile_pattern(pattern)
        return True
    except re.error:
        return False


def error_of(pattern: str) -> str | None:
    try:
        compile_pattern(pattern)
        return None
    except re.error as exc:
        return str(exc)
