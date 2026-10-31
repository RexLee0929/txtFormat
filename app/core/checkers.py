"""文本问题检查器（错别字、的得地、拼音、繁体、引号、括号、标点）。

每个检查器返回 :class:`Issue` 列表，界面据此高亮并给出修改建议。
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass

from . import encoding as enc
from . import punct, zhconv
from .paths import data_dir, find_user_file


@dataclass(slots=True)
class Issue:
    start: int
    end: int
    text: str
    kind: str
    suggestion: str = ""
    note: str = ""

    @property
    def length(self) -> int:
        return self.end - self.start


# --------------------------------------------------------------- 错别字
_TYPO_CACHE: dict[str, str] | None = None


def _typo_path() -> str:
    return find_user_file("typos.txt") or os.path.join(data_dir(), "typos.txt")


def load_typos() -> dict[str, str]:
    global _TYPO_CACHE
    if _TYPO_CACHE is not None:
        return _TYPO_CACHE
    table: dict[str, str] = {}
    raw = enc.read_text_any(_typo_path())
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        wrong, right = line.split("=", 1)
        wrong, right = wrong.strip(), right.strip()
        if wrong and right and wrong != right:
            table[wrong] = right
    _TYPO_CACHE = table
    return table


def check_typos(text: str, limit: int = 5000) -> list[Issue]:
    table = load_typos()
    if not table:
        return []
    issues: list[Issue] = []
    seen_spans: set[int] = set()
    # 长词优先，避免“不可思议”被短词切碎
    for wrong in sorted(table, key=len, reverse=True):
        start = 0
        while True:
            idx = text.find(wrong, start)
            if idx < 0:
                break
            start = idx + len(wrong)
            if any(pos in seen_spans for pos in range(idx, idx + len(wrong))):
                continue
            seen_spans.update(range(idx, idx + len(wrong)))
            issues.append(Issue(idx, idx + len(wrong), wrong, "错别字", table[wrong]))
            if len(issues) >= limit:
                issues.sort(key=lambda x: x.start)
                return issues
    issues.sort(key=lambda x: x.start)
    return issues


# --------------------------------------------------------------- 的得地
#: “副词 + 的 + 动词”应为“地”
_ADVERB_DE = (
    "慢慢|悄悄|轻轻|默默|静静|偷偷|狠狠|渐渐|缓缓|远远|紧紧|深深|冷冷|淡淡|微微|"
    "悄悄|徐徐|悠悠|匆匆|缓缓|暗暗|死死|牢牢|稳稳|飞快|默默|纷纷|悄悄|愤愤|"
    "狠狠|缓缓|呆呆|愣愣|痴痴|喃喃|颤颤|幽幽|懒懒|软软|硬硬|轻轻|匆匆|闷闷"
)
_DEDI_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(rf"(?:{_ADVERB_DE})的(?=[\u4e00-\u9fa5])"),
        "地",
        "状语应使用“地”",
    ),
    (
        re.compile(r"(?:跑|走|说|讲|笑|哭|唱|跳|飞|打|做|写|画|看|听|睡|吃|喝|学|想|长|来|去|站|坐|躺|活|死|干|办|弄|搞|数|算)的(?:好|快|慢|早|晚|远|近|高|低|多|少|对|错|很|真|不错|不轻|要命|厉害|出色|漂亮|干净|清楚|明白|透彻)"),
        "得",
        "补语应使用“得”",
    ),
    (
        re.compile(r"(?:认真|努力|细心|耐心|高兴|伤心|生气|兴奋|激动|紧张|小心|大声|小声|飞快|迅速|缓慢|安静|平静|客气|亲切|热情|冷淡|傲慢|温柔|凶狠|恶狠狠|笑眯眯)的(?=(?:说|道|问|答|看|望|听|想|笑|哭|走|跑|站|坐|喊|叫|摇头|点头|皱眉|挥手))"),
        "地",
        "状语应使用“地”",
    ),
    (
        re.compile(r"[\u4e00-\u9fa5]{1,3}的(?=(?:很|非常|十分|特别|极))"),
        "得",
        "程度补语应使用“得”",
    ),
]


def check_dedi(text: str) -> list[Issue]:
    issues: list[Issue] = []
    for rx, suggest, note in _DEDI_RULES:
        for m in rx.finditer(text):
            hit = m.group(0)
            idx = hit.rfind("的")
            if idx < 0:
                continue
            pos = m.start() + idx
            issues.append(Issue(pos, pos + 1, "的", "的得地", suggest, note))
    issues.sort(key=lambda x: x.start)
    # 去重
    out: list[Issue] = []
    last = -2
    for it in issues:
        if it.start != last:
            out.append(it)
            last = it.start
    return out


# --------------------------------------------------------------- 拼音
_PINYIN_RX = re.compile(
    r"[a-zA-Z]*[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜêńň][a-zA-Z]*"
    r"|\b[a-zA-Z]{1,6}[1-4]\b"
)


def check_pinyin(text: str) -> list[Issue]:
    out: list[Issue] = []
    for m in _PINYIN_RX.finditer(text):
        if len(m.group(0)) <= 12:
            out.append(Issue(m.start(), m.end(), m.group(0), "拼音", "", "疑似拼音注音，请确认是否应还原为汉字"))
    return out


# --------------------------------------------------------------- 繁体
def check_traditional(text: str, limit: int = 3000) -> list[Issue]:
    out: list[Issue] = []
    for pos, orig, simp in zhconv.traditional_chars(text)[:limit]:
        out.append(Issue(pos, pos + 1, orig, "繁体字", simp, "可用“简繁转换”统一转为简体"))
    return out


# --------------------------------------------------------------- 引号/括号
def check_quotes(text: str) -> list[Issue]:
    out: list[Issue] = []
    for m in re.finditer(r"“[^”\n]*\n[^\n]*?”|‘[^’\n]*\n[^\n]*?’", text):
        out.append(Issue(m.start(), m.end(), m.group(0)[:20], "引号不匹配", "", "引号跨行且未配对"))
    for m in re.finditer(r"“[^“”\n]{0,300}“[^“”\n]{0,300}”", text):
        out.append(Issue(m.start(), m.end(), m.group(0)[:20], "嵌套引号", "", "双引号内部又出现双引号"))
    return out


_PAIRS = {"（": "）", "(": ")", "【": "】", "《": "》", "“": "”", "‘": "’"}


def check_brackets(text: str) -> list[Issue]:
    out: list[Issue] = []
    for m in re.finditer(r"[\u4e00-\u9fa5][\(\)（）【】《》][\u4e00-\u9fa5]", text):
        out.append(Issue(m.start(), m.end(), m.group(0), "半个括号", "", "句中只有半个括号"))
    # 统计配对
    for left, right in (("（", "）"), ("(", ")"), ("【", "】"), ("《", "》")):
        if text.count(left) != text.count(right):
            pos = text.find(left) if text.count(left) > text.count(right) else text.find(right)
            if pos >= 0:
                out.append(Issue(pos, pos + 1, text[pos], "括号不匹配",
                                 "", f"“{left}”出现 {text.count(left)} 次，“{right}”出现 {text.count(right)} 次"))
    return out


# --------------------------------------------------------------- 标点
# 规则表在 punct.PUNCT_RULES（与「格式整理」的改写步骤同一份数据源），
# 这里只负责把命中包装成 Issue，不再各写一套正则。
def check_punct(text: str) -> list[Issue]:
    out: list[Issue] = []
    for m in punct.illegal_punct_rx().finditer(text):
        out.append(Issue(m.start(), m.end(), m.group(0), "不规则标点",
                         punct.describe(text, m), "标点使用不符合 GB/T 15834—2011"))
    return out


# --------------------------------------------------------------- 空白行
def check_long_lines(text: str, max_chars: int = 340) -> list[Issue]:
    out: list[Issue] = []
    for m in re.finditer(rf"[^\n]{{{max_chars},}}", text):
        out.append(Issue(m.start(), m.start() + 1, m.group(0)[:20], "超长段落",
                         "", f"该行 {len(m.group(0))} 字，可能缺少分段或标点"))
    return out


# --------------------------------------------------------------- 注册表
CHECKERS: dict[str, tuple[str, Callable[[str], list[Issue]]]] = {
    "typos": ("常见错别字", check_typos),
    "dedi": ("的得地误用", check_dedi),
    "pinyin": ("拼音", check_pinyin),
    "traditional": ("繁体字", check_traditional),
    "quotes": ("引号不匹配", check_quotes),
    "brackets": ("括号问题", check_brackets),
    "punct": ("不规则标点", check_punct),
    "longline": ("超长段落", check_long_lines),
}


def run_checker(key: str, text: str) -> list[Issue]:
    item = CHECKERS.get(key)
    if not item:
        return []
    return item[1](text)


__all__ = ["Issue", "CHECKERS", "run_checker", "load_typos",
           "check_typos", "check_dedi", "check_pinyin", "check_traditional",
           "check_quotes", "check_brackets", "check_punct", "check_long_lines"]
