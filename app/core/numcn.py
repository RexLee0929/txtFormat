"""中文数字与阿拉伯数字互转，以及章节标题规范化。

原程序的“规范化章节标题”能把 ``第032章`` / ``第０３２章`` / ``第零三二章``
统一转换成 ``第三十二章``；这里提供可逆的双向转换。
"""

from __future__ import annotations

import re

CN_DIGITS = "零一二三四五六七八九"
CN_UNITS = ["", "十", "百", "千"]
CN_BIG = ["", "万", "亿", "万亿"]

_CHAR_MAP = {
    "○": "零", "〇": "零", "０": "零", "O": "零", "o": "零",
    "两": "二", "壹": "一", "贰": "二", "贰": "二", "叁": "三", "參": "三",
    "肆": "四", "伍": "五", "陆": "六", "陸": "六", "柒": "七", "捌": "八",
    "玖": "九", "拾": "十",
}
_FULLWIDTH = {chr(0xFF10 + i): str(i) for i in range(10)}


def int_to_cn(num: int, use_liang: bool = False) -> str:
    """整数转中文小写数字（支持 0 ~ 9999_9999_9999）。"""
    if num == 0:
        return "零"
    if num < 0:
        return "负" + int_to_cn(-num, use_liang)
    # 按 4 位一节拆分
    sections: list[int] = []
    n = num
    while n > 0:
        sections.append(n % 10000)
        n //= 10000
    if len(sections) > len(CN_BIG):
        return str(num)

    parts: list[str] = []
    need_zero = False
    for idx in range(len(sections) - 1, -1, -1):
        sec = sections[idx]
        if sec == 0:
            need_zero = True
            continue
        sec_text = _section_to_cn(sec)
        if parts and (need_zero or sec < 1000):
            parts.append("零")
        parts.append(sec_text + CN_BIG[idx])
        need_zero = False
    text = "".join(parts)
    # “一十五” → “十五”（口语习惯，章节号里更常见）
    if text.startswith("一十"):
        text = text[1:]
    if use_liang:
        text = text.replace("二", "两", 1) if text.startswith("二") else text
    return text


def _section_to_cn(sec: int) -> str:
    out: list[str] = []
    zero = False
    for pos in range(3, -1, -1):
        digit = (sec // (10 ** pos)) % 10
        if digit == 0:
            if out:
                zero = True
            continue
        if zero:
            out.append("零")
            zero = False
        out.append(CN_DIGITS[digit] + CN_UNITS[pos])
    return "".join(out)


def cn_to_int(text: str) -> int | None:
    """中文数字转整数；无法解析返回 None。"""
    if not text:
        return None
    s = "".join(_CHAR_MAP.get(ch, ch) for ch in text.strip())
    s = "".join(_FULLWIDTH.get(ch, ch) for ch in s)
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if not re.fullmatch(r"[零一二三四五六七八九十百千万亿]+", s):
        return None

    total = 0
    section = 0
    number = 0
    for ch in s:
        if ch in CN_DIGITS:
            number = CN_DIGITS.index(ch)
        elif ch in ("十", "百", "千"):
            unit = {"十": 10, "百": 100, "千": 1000}[ch]
            if number == 0:
                number = 1
            section += number * unit
            number = 0
        elif ch in ("万", "亿"):
            section += number
            number = 0
            total += section * (10000 if ch == "万" else 100000000)
            section = 0
    return total + section + number


def mixed_to_int(text: str) -> int | None:
    """兼容“第1章”“第１章”“第一章”“第零三二章”“第032章”。"""
    if text is None:
        return None
    s = text.strip()
    s = "".join(_FULLWIDTH.get(ch, ch) for ch in s)
    s = s.replace("－", "-").replace("—", "-").replace("―", "-")
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"[零一二三四五六七八九十百千万亿两壹贰叁肆伍陆柒捌玖拾○〇]+", s):
        # “零三二”这类逐位写法
        if s.startswith("零") and all(c in CN_DIGITS for c in s):
            return int("".join(str(CN_DIGITS.index(c)) for c in s))
        return cn_to_int(s)
    return None


def int_to_chapter_cn(num: int) -> str:
    return int_to_cn(num)


__all__ = ["int_to_cn", "cn_to_int", "mixed_to_int", "int_to_chapter_cn", "CN_DIGITS"]
