"""格式整理引擎。

对应原程序“格式整理”按钮，依次完成：

1. 除去每行行尾的空格（半角、全角、制表符）
2. 需要时按句号重新分段
3. 按设置转换标点 / 英文字符 / 数值的全角半角
4. 除去非标题行中的空格
5. 处理硬回车（把被硬回车截断的行续回上一行）
6. 把 ``&#29234;`` 这类 Unicode 码转成汉字
7. 除去可识别的广告
8. 按设置应用排版样式（行首缩进、段落间隔）
9. 还原屏蔽码
10. 还原拼音
11. 规范标点组合
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from . import encoding as enc
from . import punct as punct_mod
from .paths import data_dir
from .settings import Settings

# ---------------------------------------------------------------- 章节标题
CN_NUM = "壹贰叁肆伍陆柒捌玖一二两三四五六七八九十○〇零百千O0-9０-９"
CHAPTER_LINE = re.compile(
    r"^[ 　\t]*(?:正文[ 　\t]*)?(?:第[―－\-─—" + CN_NUM + r"]{1,12}[章节節回集卷部篇]"
    r"|[" + CN_NUM + r"]{1,12}[、\.．][ 　\t]*\S"
    r"|[（(][" + CN_NUM + r"]{1,12}[）)])"
)
_TERMINATORS = "。！？…”’）】》」』!?.”)】 \t"

#: 广告行特征（整行匹配才删除，避免误伤正文）
_AD_LINE_PATTERNS = [
    re.compile(r"^[ 　\t]*.{0,60}更新时间.{1,40}(?:本章)?字数.{0,20}$"),
    re.compile(r"^[ 　\t]*(?: )?字数[:：][0-9０-９.]+\s*$"),
    re.compile(r"^[ 　\t]*(?:本章未完|未完待续|求收藏|求推荐|求月票|求订阅|求打赏|求票).{0,20}$"),
    re.compile(r"^[ 　\t]*(?:手机|电脑|wap)?(?:用户)?请?(?:访问|登陆|登录|浏览).{0,30}$"),
    re.compile(r"^[ 　\t]*(?:www|wap|m)\.[a-z0-9\-]+\.[a-z]{2,6}.*$", re.I),
    re.compile(r"^[ 　\t]*(?:https?://|ftp://)\S+\s*$", re.I),
    re.compile(r"^[ 　\t]*[（(][^）)]{0,40}(?:推荐|收藏|订阅|支持|更新|稳定|免费)[^）)]{0,40}[）)]\s*$"),
    re.compile(r"^[ 　\t]*(?:☆|★|※|◆|◇)[^\n]{0,60}(?:网|站|吧|城|阁|苑|屋|库)[^\n]{0,20}$"),
]
_AD_INLINE = [
    re.compile(r"(?:https?://|www\.)[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=%]{4,}"),
    re.compile(r"(?:手机|电脑)用户请?(?:访问|登陆|登录)[^\n，。]{0,30}"),
    re.compile(r"字数[:：][0-9０-９.]+\s*"),
    re.compile(r"[（(]?(?:本章未完|未完待续)[）)]?\s*"),
]

_UNICODE_CODE = re.compile(r"(?:[&＆])?(?:amp)?[#＃]([xX])?([0-9a-fA-F０-９]{2,8})[;；]")


@dataclass
class FormatStats:
    removed_tail_spaces: int = 0
    joined_lines: int = 0
    removed_ads: int = 0
    converted_codes: int = 0
    indented: int = 0
    restored_screened: int = 0
    restored_pinyin: int = 0

    def as_text(self) -> str:
        bits = []
        if self.removed_tail_spaces:
            bits.append(f"清理行尾空格 {self.removed_tail_spaces} 行")
        if self.joined_lines:
            bits.append(f"合并硬回车 {self.joined_lines} 处")
        if self.removed_ads:
            bits.append(f"删除广告 {self.removed_ads} 处")
        if self.converted_codes:
            bits.append(f"还原 Unicode 码 {self.converted_codes} 处")
        if self.restored_screened:
            bits.append(f"还原屏蔽码 {self.restored_screened} 处")
        if self.restored_pinyin:
            bits.append(f"还原拼音 {self.restored_pinyin} 处")
        return "；".join(bits)


@dataclass
class FormatResult:
    text: str
    stats: FormatStats = field(default_factory=FormatStats)
    changed: bool = False


# ---------------------------------------------------------------- 辅助数据
_PAIRS_CACHE: dict[str, tuple[float, list[tuple[str, str]]]] = {}


def _load_pairs(filename: str) -> list[tuple[str, str]]:
    """读 ``app/data/<filename>`` 的 “旧=新” 对照表（带缓存）。

    原来每次格式整理都要重新读盘 + 逐行解析（screened.txt / pinyin.txt
    可能几千行），一按按钮就白花几十毫秒；表内容只跟文件 mtime 有关，
    按 mtime 缓存即可。
    """
    path = os.path.join(data_dir(), filename)
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return []
    cached = _PAIRS_CACHE.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    pairs: list[tuple[str, str]] = []
    raw = enc.read_text_any(path)
    for line in (raw or "").splitlines():
        line = line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        left, right, *_ = line.split("=")
        if left.strip():
            pairs.append((left.strip(), right.strip()))
    _PAIRS_CACHE[path] = (stamp, pairs)
    return pairs


# ---------------------------------------------------------------- 各步骤
def is_chapter_line(line: str) -> bool:
    return bool(CHAPTER_LINE.match(line))


def _ends_sentence(line: str) -> bool:
    stripped = line.rstrip(" 　\t")
    return bool(stripped) and stripped[-1] in _TERMINATORS


def _convert_charset(text: str, mode: str) -> str:
    """英文字符全角/半角。"""
    if mode == "keep":
        return text
    out: list[str] = []
    for ch in text:
        if mode == "full":
            if "a" <= ch <= "z":
                out.append(chr(ord(ch) + 0xFEE0))
            elif "A" <= ch <= "Z":
                out.append(chr(ord(ch) + 0xFEE0))
            else:
                out.append(ch)
        else:  # half
            code = ord(ch)
            if 0xFF41 <= code <= 0xFF5A or 0xFF21 <= code <= 0xFF3A:
                out.append(chr(code - 0xFEE0))
            else:
                out.append(ch)
    return "".join(out)


def _convert_numbers(text: str, mode: str) -> str:
    if mode == "keep":
        return text
    out: list[str] = []
    for ch in text:
        if mode == "full":
            out.append(chr(ord(ch) + 0xFEE0) if "0" <= ch <= "9" else ch)
        else:
            code = ord(ch)
            out.append(chr(code - 0xFEE0) if 0xFF10 <= code <= 0xFF19 else ch)
    return "".join(out)


def convert_unicode_codes(text: str) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        is_hex = bool(m.group(1))
        digits = m.group(2)
        digits = digits.translate({0xFF10 + i: ord("0") + i for i in range(10)})
        try:
            code = int(digits, 16) if is_hex else int(digits, 10)
        except ValueError:
            return m.group(0)
        if 0 < code <= 0x10FFFF:
            count += 1
            try:
                return chr(code)
            except ValueError:
                return m.group(0)
        return m.group(0)

    return _UNICODE_CODE.sub(repl, text), count


def strip_ads(text: str) -> tuple[str, int]:
    removed = 0
    out_lines: list[str] = []
    for line in text.split("\n"):
        if any(p.match(line) for p in _AD_LINE_PATTERNS):
            removed += 1
            continue
        new_line = line
        for p in _AD_INLINE:
            new_line, n = p.subn("", new_line)
            removed += n
        out_lines.append(new_line.rstrip())
    return "\n".join(out_lines), removed


def restore_screened(text: str) -> tuple[str, int]:
    count = 0
    for masked, original in _load_pairs("screened.txt"):
        pattern = r"\*+".join(re.escape(part) for part in re.split(r"\*+", masked))
        if not pattern.strip():
            continue
        text, n = re.subn(pattern, original, text)
        count += n
    return text, count


def restore_pinyin(text: str) -> tuple[str, int]:
    count = 0
    for pinyin, hanzi in sorted(_load_pairs("pinyin.txt"), key=lambda x: -len(x[0])):
        pattern = r"(?<![A-Za-z])" + re.escape(pinyin).replace(r"\ ", r"\s*") + r"(?![A-Za-z])"
        text, n = re.subn(pattern, hanzi, text, flags=re.IGNORECASE)
        count += n
    return text, count


def apply_indent(lines: list[str], settings: Settings) -> tuple[list[str], int]:
    indent = settings.indent_text
    if not indent:
        return lines, 0
    out: list[str] = []
    changed = 0
    for line in lines:
        if not line.strip() or is_chapter_line(line):
            out.append(line)
            continue
        if line.startswith(indent):
            out.append(line)
            continue
        out.append(indent + line.lstrip(" 　\t"))
        changed += 1
    return out, changed


def apply_paragraph_spacing(lines: list[str], mode: str) -> list[str]:
    if mode == "none":       # 不隔行：删除空行
        return [ln for ln in lines if ln.strip()]
    if mode == "blank":      # 隔一行：段落之间插入一个空行
        out: list[str] = []
        for ln in lines:
            if ln.strip() and out and out[-1].strip():
                out.append("")
            out.append(ln)
        return out
    return lines


def split_by_period(text: str) -> str:
    return re.sub(r"([。！？…](?:’)?(?:”)?)(?![\n”’）】])", r"\1\n", text)


def _looks_like_ad(line: str) -> bool:
    return any(p.match(line) for p in _AD_LINE_PATTERNS)


def join_hard_returns(lines: list[str], width: int) -> tuple[list[str], int]:
    """把被硬回车截断的行续回上一行。

    判定条件（与原程序一致）：当前行不是章节标题、行尾不是句末标点、
    且长度超过设定行宽；此时把下一行接上来，直到行尾出现句末标点。
    广告行/字数行不参与合并，避免把页眉页脚并进正文。
    """
    out: list[str] = []
    joined = 0
    i = 0
    total = len(lines)
    while i < total:
        line = lines[i]
        guard = 0
        while i + 1 < total and guard < 50:
            nxt = lines[i + 1]
            if not line.strip() or not nxt.strip():
                break
            if is_chapter_line(line) or is_chapter_line(nxt):
                break
            if _looks_like_ad(line) or _looks_like_ad(nxt):
                break
            if _ends_sentence(line):
                break
            if len(line.strip()) <= width:
                break
            line = line.rstrip() + nxt.strip(" 　\t")
            joined += 1
            guard += 1
            i += 1
        out.append(line)
        i += 1
    return out, joined


def format_text(text: str, settings: Settings) -> FormatResult:
    stats = FormatStats()
    original = text

    # 1. 行尾空格
    before = text
    text = punct_mod.rstrip_lines(text)
    if text != before:
        stats.removed_tail_spaces = sum(
            1 for a, b in zip(before.split("\n"), text.split("\n")) if a != b
        )

    # 2. 以句号分段
    if settings.split_by_period:
        text = split_by_period(text)

    # 3. 标点 / 英文 / 数值
    text = punct_mod.convert_punct(text, settings.punct_mode)
    text = _convert_charset(text, settings.english_mode)
    text = _convert_numbers(text, settings.number_mode)

    # 4. 中文间空格
    if settings.remove_spaces_in_text:
        text = punct_mod.strip_chinese_spaces(text)

    # 5. 硬回车
    lines = text.split("\n")
    if settings.auto_hard_return:
        lines, stats.joined_lines = join_hard_returns(lines, max(10, settings.hard_return_width))
        text = "\n".join(lines)

    # 6. Unicode 码
    if settings.convert_unicode_code:
        text, stats.converted_codes = convert_unicode_codes(text)

    # 7. 广告
    if settings.has_ad:
        text, stats.removed_ads = strip_ads(text)

    # 9/10. 屏蔽码与拼音（先还原再排版，避免缩进被误伤）
    if settings.restore_screened:
        text, stats.restored_screened = restore_screened(text)
    if settings.restore_pinyin:
        text, stats.restored_pinyin = restore_pinyin(text)

    # 11. 标点组合
    if settings.fix_punct_combo:
        text = punct_mod.fix_illegal_punct(text)
        text = punct_mod.balance_quotes(text)
        text = punct_mod.common_punct_fixups(text)

    # 8. 排版
    lines = text.split("\n")
    lines, stats.indented = apply_indent(lines, settings)
    lines = apply_paragraph_spacing(lines, settings.para_spacing)
    text = "\n".join(lines)

    # 收尾：去掉空行里的空格
    text = re.sub(r"[ 　\t]+\n", "\n", text)
    if not text.endswith("\n"):
        text += "\n"

    return FormatResult(text, stats, changed=text != original)


__all__ = [
    "FormatStats", "FormatResult", "format_text", "is_chapter_line",
    "strip_ads", "convert_unicode_codes", "join_hard_returns",
    "restore_screened", "restore_pinyin", "CHAPTER_LINE",
]
