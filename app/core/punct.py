"""标点符号处理（全角/半角转换、非法组合修正、引号规范化）。

依据 GB/T 15834—2011《标点符号用法》，与原程序的处理口径保持一致：
数字之间的小数点、英文字符之间的标点、URL 中的冒号等在转换时跳过。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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

# --------------------------------------------------------------- 非法标点
@dataclass(frozen=True, slots=True)
class PunctRule:
    """一条「非法标点」知识。

    **唯一数据源**：以前「一键审核」（checkers.check_punct）和「格式整理」
    （fix_illegal_punct）各写一份规则，两边会漂移 —— 检查器报的错整理器不修、
    整理器改的地方检查器又不报。现在一条规则同时带 ``detect``（定位）和
    ``fix``（改写步骤），两个方向读同一张表。

    ``detect`` 会被拼进联合正则，因此**不许含反向引用**（``\\1`` 这类）；
    需要反向引用的精确改写放在 ``fix`` 里单独跑，不参与拼接。
    """

    name: str                                   # 问题名称，审核表里直接显示
    detect: str                                 # 检测正则（无反向引用）
    fix: tuple[tuple[str, str], ...] = ()       # 改写步骤：(匹配式, 替换式)；空 = 只报不修


#: 顺序有意义：**改写按顺序依次执行**，检测也按此顺序拼联合式（长的放前面，
#: 否则 ``．`` 会先于 ``[。．\.]{2,}`` 命中，把连续点切成单个）。
PUNCT_RULES: tuple[PunctRule, ...] = (
    PunctRule("连续句号（应为省略号）", r"[。．\.]{2,}",
              ((r"[。．\.]{2,}", "……"),)),
    PunctRule("省略号过长", r"…{3,}", ((r"…{3,}", "……"),)),
    PunctRule("单省略号（应为双）", r"(?<!…)…(?!…)"),
    PunctRule("标点重复", r"[，、；：！？]{2,}",
              ((r"([，。、；：！？])\1+", r"\1"),)),
    PunctRule("标点混用连续", r"[，。；：、]{2,}",
              ((r"([，。；：、]){2,}", r"\1"),)),
    PunctRule("句号与逗号/分号/冒号连用", r"。[ \t]*[，、；：]|[，、；：][ \t]*。",
              ((r"。[ \t]*[，、；：]", "。"), (r"[，、；：][ \t]*。", "。"))),
    PunctRule("问号叹号连用", r"？[！!]+|！！+|？？+",
              ((r"？[！!]+", "？！"), (r"！！+", "！！"), (r"？？+", "？？"))),
    PunctRule("半角句点（应为句号）", r"．", ((r"．", "。"),)),
    PunctRule("句末多余逗号", r"，(?=[。！？])", ((r"，(?=[。！？])", ""),)),
    PunctRule("句号后多余逗号", r"。(?=[，、])", ((r"。(?=[，、])", ""),)),
    PunctRule("重复冒号", r"：{2,}", ((r"：：+", "："),)),
    PunctRule("重复引号", r"“{2,}|”{2,}|‘‘|’’",
              ((r"““+", "“"), (r"””+", "”"))),
    PunctRule("引号方向/用法错误", r"：”|：’|''|\"\""),
    PunctRule("书名号内出现句号", r"《[\u4e00-\u9fa5]{1,40}[。\.][\u4e00-\u9fa5]{1,40}》"),
    PunctRule("异体标点", r"[﹑﹁﹂﹄﹃︵︶︻︼︰]"),
    PunctRule("连续半角标点", r"[．\.。，\,、·`]{2,}"),
)


def _build_detect() -> re.Pattern[str]:
    parts = [f"(?:{rule.detect})" for rule in PUNCT_RULES if rule.detect]
    return re.compile("|".join(parts))


#: 联合检测式：一次扫描命中所有规则，重叠的位置天然只报一条（后一条规则
#: 若与前面命中同一片段，不会重复报）。
_ILLEGAL_PUNCT_RX = _build_detect()

#: (预编译检测式, 名称)，供 :func:`describe` 回溯归类用（不重复编译）
_DETECT_RULES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rule.detect), rule.name) for rule in PUNCT_RULES if rule.detect)


def illegal_punct_rx() -> re.Pattern[str]:
    return _ILLEGAL_PUNCT_RX


def describe(text: str, match: re.Match[str]) -> str:
    """这条命中属于哪一类（用于审核表里的说明列）。"""
    start, end = match.span()
    for rx, name in _DETECT_RULES:
        m = rx.match(text, start)
        if m is not None and m.end() == end:
            return name
    return "不规则标点"


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
    """修正常见的非法标点组合（步骤来自 :data:`PUNCT_RULES`，与审核同源）。"""
    result = text
    for rule in PUNCT_RULES:
        for pattern, repl in rule.fix:
            result = re.sub(pattern, repl, result)
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
    "PunctRule", "PUNCT_RULES", "illegal_punct_rx", "describe",
]
