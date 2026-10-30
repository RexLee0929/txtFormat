"""标点符号处理（全角/半角转换、非法组合修正、引号规范化）。

依据 GB/T 15834—2011《标点符号用法》，与原程序的处理口径保持一致：
数字之间的小数点、英文字符之间的标点、URL 中的冒号等在转换时跳过。
"""

from __future__ import annotations

import re

#: 半角 → 全角（中文语境下的对应关系）
HALF_TO_FULL = {
    ",": "，", ".": "。", "?": "？", "!": "！", ":": "：", ";": "；",
    "(": "（", ")": "）", "~": "～", "'": "’", '"': "”",
}
FULL_TO_HALF = {v: k for k, v in HALF_TO_FULL.items()}
FULL_TO_HALF.update({"‘": "'", "“": '"'})

#: 这些半角符号永远不参与“转全角”（程序符号、URL 组成部分等）
_PUNCT_SKIP = set("/-*|\\^@#&[]<>_=+$%`")
#: 允许出现在它们两侧的字符（字母、数字、全角数字）
_ALNUM = r"A-Za-z0-9０-９\u00c0-\u024f\u0370-\u03ff\u0400-\u04ff"

#: 常见非法标点组合 → 修正结果（顺序有意义）
_ILLEGAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[。．\.]{2,}"), "……"),                # 连续句号 → 省略号
    (re.compile(r"[．\.]{2,}"), "……"),
    (re.compile(r"…{3,}"), "……"),
    (re.compile(r"([，。、；：！？])\1+"), r"\1"),          # ，，， → ，
    (re.compile(r"([，。；：、]){2,}"), r"\1"),             # 混用连续标点
    (re.compile(r"。[ \t]*[，、；：]"), "。"),
    (re.compile(r"[，、；：][ \t]*。"), "。"),
    (re.compile(r"？[！!]+"), "？！"),
    (re.compile(r"！！+"), "！！"),
    (re.compile(r"？？+"), "？？"),
    (re.compile(r"．"), "。"),
    (re.compile(r"，(?=[。！？])"), ""),
    (re.compile(r"。(?=[，、])"), ""),
    (re.compile(r"：：+"), "："),
    (re.compile(r"““+"), "“"),
    (re.compile(r"””+"), "”"),
]


def _neighbors(text: str, i: int) -> tuple[str, str]:
    return (text[i - 1] if i > 0 else ""), (text[i + 1] if i + 1 < len(text) else "")


def _is_alnum(ch: str) -> bool:
    return bool(ch) and bool(re.match(rf"[{_ALNUM}]", ch))


def _should_skip(text: str, i: int, ch: str, upper: bool) -> bool:
    prev, nxt = _neighbors(text, i)
    if ch in _PUNCT_SKIP:
        return True
    # 完全夹在英文/数字之间：属于西文语境，一律不动
    if _is_alnum(prev) and _is_alnum(nxt):
        return True
    if ch == ".":
        # 小数点 / 省略号 / 英文缩写 / 数字前后的点
        if prev.isdigit() and nxt.isdigit():
            return True
        if _is_alnum(prev) or _is_alnum(nxt):
            return True
    if ch in ("?", "%"):
        if _is_alnum(prev) or _is_alnum(nxt):
            return True
    if ch == ":":
        if text[max(0, i - 4):i].lower().endswith("http"):
            return True
        if _is_alnum(prev) or _is_alnum(nxt):
            return True
    if ch == ";":
        if _is_alnum(prev) or prev in ("&", "&amp;"):
            return True
    if ch in ("'", '"'):
        if _is_alnum(prev) and _is_alnum(nxt):
            return True
    if _is_alnum(prev) or _is_alnum(nxt):
        # 中文标点夹在英文/数字中不动（逗号除外：数字后紧跟中文时仍应转全角）
        if ch in ".?!":
            return True
    return False


def to_fullwidth_punct(text: str) -> str:
    out = list(text)
    for i, ch in enumerate(out):
        rep = HALF_TO_FULL.get(ch)
        if rep and not _should_skip(text, i, ch, True):
            out[i] = rep
    return "".join(out)


def to_halfwidth_punct(text: str) -> str:
    out = list(text)
    for i, ch in enumerate(out):
        rep = FULL_TO_HALF.get(ch)
        if rep and not _should_skip(text, i, ch, False):
            out[i] = rep
    return "".join(out)


def convert_punct(text: str, mode: str) -> str:
    """mode: 'full' | 'half' | 'keep'"""
    if mode == "full":
        return to_fullwidth_punct(text)
    if mode == "half":
        return to_halfwidth_punct(text)
    return text


def fix_illegal_punct(text: str) -> str:
    """修正常见的非法标点组合。"""
    result = text
    for pattern, repl in _ILLEGAL_PATTERNS:
        result = pattern.sub(repl, result)
    return result


def strip_chinese_spaces(text: str, keep_title_space: bool = True) -> str:
    """删除中文之间的半角空格、全角空格与制表符。"""
    if keep_title_space:
        pattern = re.compile(
            r"(?<![\n0-9A-Za-z０-９Ａ-Ｚａ-ｚ 　\t章节節回集卷文篇部])"
            r"[ 　\t]+"
            r"(?![0-9A-Za-z０-９Ａ-Ｚａ-ｚ 　\t第])"
        )
    else:
        pattern = re.compile(r"(?<![\n0-9A-Za-z０-９Ａ-Ｚａ-ｚ 　\t])[ 　\t]+(?![0-9A-Za-z０-９Ａ-Ｚａ-ｚ 　\t])")
    return pattern.sub("", text)


def rstrip_lines(text: str) -> str:
    """去掉每行行尾的半角空格、全角空格、制表符。"""
    return re.sub(r"[ 　\t]+(?=\n|$)", "", text)


_QUOTE_PAIRS = {"“": "”", "‘": "’", "（": "）", "《": "》", "【": "】", "(": ")", "[": "]"}


def balance_quotes(text: str) -> str:
    """把“同向”的引号规范为相向（由一顺变为相向）：``“..“`` → ``“..”``。"""
    result = text
    for left, right in (("“", "”"), ("‘", "’")):
        # 行内：左引号出现后若又以左引号收尾，则改右引号
        result = re.sub(
            rf"{left}([^{left}{right}\n]{{0,400}}){left}",
            lambda m, l=left, r=right: f"{l}{m.group(1)}{r}",
            result,
        )
    return result


def common_punct_fixups(text: str) -> str:
    """一批“几乎总是错”的标点修正（格式整理第 11 步）。"""
    result = text
    # 冒号后面直接换行再跟左引号
    result = re.sub(r"：\n(?:[ 　\t]+)?“", "：“", result)
    # 行尾右引号前缺标点
    result = re.sub(r"([\u4e00-\u9fa5])”(?=\n)", r"\1！”", result)
    # 引号单独成行
    result = re.sub(r"：“\n[ 　\t]+", "：“", result)
    return result


__all__ = [
    "convert_punct", "to_fullwidth_punct", "to_halfwidth_punct",
    "fix_illegal_punct", "strip_chinese_spaces", "rstrip_lines",
    "balance_quotes", "common_punct_fixups", "HALF_TO_FULL",
]
