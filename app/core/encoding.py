"""文本文件编码识别与读写。

设计要点
--------
* 内部一律使用 ``\\n`` 换行的字符串（与 QTextDocument 一致）；
  读入时记录原始行尾风格，保存时还原。
* 支持：UTF-8 / UTF-8 BOM / UTF-16 LE / UTF-16 BE / GB18030(GBK) / ANSI 兜底。
* ``keep_bom`` 决定保存时是否写 BOM。
"""

from __future__ import annotations

import codecs
import os
from dataclasses import dataclass

BOM_UTF8 = codecs.BOM_UTF8
BOM_UTF16_LE = codecs.BOM_UTF16_LE
BOM_UTF16_BE = codecs.BOM_UTF16_BE

#: 界面上可选的“保存编码”
ENCODINGS: list[tuple[str, str]] = [
    ("ANSI (GBK/GB18030)", "gb18030"),
    ("UTF-8", "utf-8"),
    ("UTF-8 BOM", "utf-8-sig"),
    ("Unicode (UTF-16 LE)", "utf-16-le"),
    ("Unicode 大尾 (UTF-16 BE)", "utf-16-be"),
]

ENCODING_LABELS = {codec: label for label, codec in ENCODINGS}


@dataclass(slots=True)
class DecodedText:
    text: str
    encoding: str          # 用于回写的 codec 名
    label: str             # 界面显示名
    newline: str           # "\r\n" / "\n" / "\r"
    has_bom: bool


def _guess_bom(data: bytes) -> tuple[str, int] | None:
    if data.startswith(BOM_UTF8):
        return "utf-8-sig", 3
    if data.startswith(BOM_UTF16_LE):
        return "utf-16-le", 2
    if data.startswith(BOM_UTF16_BE):
        return "utf-16-be", 2
    return None


def detect_encoding(data: bytes) -> str:
    """返回最可能的 codec 名。"""
    bom = _guess_bom(data)
    if bom:
        return bom[0]
    if not data:
        return "utf-8"
    # 纯 ASCII 一律视为 UTF-8（与 ANSI 等价）
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    for codec in ("gb18030",):
        try:
            data.decode(codec)
            return codec
        except UnicodeDecodeError:
            pass
    return "latin-1"


def detect_newline(text: str) -> str:
    crlf = text.count("\r\n")
    cr = text.count("\r") - crlf
    lf = text.count("\n") - crlf
    if crlf >= lf and crlf >= cr:
        return "\r\n"
    if cr > lf:
        return "\r"
    return "\n"


def decode(data: bytes, encoding: str | None = None) -> DecodedText:
    bom = _guess_bom(data)
    codec = encoding or (bom[0] if bom else detect_encoding(data))
    has_bom = codec == "utf-8-sig" or (bom is not None and bom[0] == codec)
    try:
        text = data.decode(codec, errors="replace")
    except LookupError:
        codec = "utf-8"
        text = data.decode(codec, errors="replace")
        has_bom = False
    if codec == "utf-8-sig":
        codec = "utf-8"
    newline = detect_newline(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.lstrip("\ufeff")
    return DecodedText(text, codec, ENCODING_LABELS.get(codec, codec.upper()), newline, has_bom)


def read_text(path: str, encoding: str | None = None) -> DecodedText:
    with open(path, "rb") as fh:
        data = fh.read()
    return decode(data, encoding)


#: 数据/用户文本文件的通用解码顺序（UTF-8 含 BOM → GB18030）
TEXT_CODECS: tuple[str, ...] = ("utf-8-sig", "gb18030")


def decode_first(data: bytes, codecs: tuple[str, ...] = TEXT_CODECS) -> str | None:
    """按给定顺序尝试解码，返回第一个成功的文本；全都失败返回 None。

    原先「for codec in (...): try decode / except continue」这段循环在
    7 个文件里各抄了一份（formatter / checkers / adfilter / regexlib /
    convert ×4），改一处永远漏另一处 —— 统一收在这里。
    """
    for codec in codecs:
        try:
            return data.decode(codec)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def read_text_any(path: str, codecs: tuple[str, ...] = TEXT_CODECS) -> str | None:
    """读一个文本文件（自动尝试多种编码）。读不到/解不出返回 None。"""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    return decode_first(data, codecs)


def encode(text: str, encoding: str, newline: str = "\r\n", keep_bom: bool = True) -> bytes:
    """把内部文本编码为字节。``encoding`` 为 codec 名。"""
    body = text.replace("\n", newline) if newline != "\n" else text
    codec = encoding
    want_bom = keep_bom
    if codec == "utf-8-sig":
        codec, want_bom = "utf-8", True
    if codec in ("utf-16-le", "utf-16-be"):
        want_bom = True  # UTF-16 必须带 BOM 才能被别的程序正确识别
    data = body.encode(codec, errors="replace")
    if want_bom:
        if codec == "utf-8" and not data.startswith(BOM_UTF8):
            data = BOM_UTF8 + data
        elif codec == "utf-16-le" and not data.startswith(BOM_UTF16_LE):
            data = BOM_UTF16_LE + data
        elif codec == "utf-16-be" and not data.startswith(BOM_UTF16_BE):
            data = BOM_UTF16_BE + data
    return data


def save_text(path: str, text: str, encoding: str = "gb18030",
              newline: str = "\r\n", keep_bom: bool = True) -> None:
    data = encode(text, encoding, newline, keep_bom)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
