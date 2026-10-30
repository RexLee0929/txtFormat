"""文件格式转换。

实现的转换器（全部为纯 Python，不依赖外部程序）：

===========================  ==========================================
Htm2txt / Html2Txt            HTML 文件转纯文本
ePub2txt                      EPUB（含 ZIP 打包）按 spine 顺序转文本
doc2txt                       DOCX（Word 2007+）转文本
Pdb2txt / Mobi2txt            PalmDoc / MOBI 文本压缩解包
Jar2txt                       JAR 电子书内嵌文本提取
Chm2htm                       CHM 解包（调用系统 hh.exe）
Rtf2txt                       RTF 简易转文本
Txt 编码转换                   ANSI / UTF-8 / UTF-16 / BOM 互转
===========================  ==========================================

其余历史格式（UMD、AZW4、EBK2…）在当前版本中会给出明确提示，不做静默失败。
"""

from __future__ import annotations

import html
import os
import re
import struct
import subprocess
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser

from . import encoding as enc


@dataclass
class ConvertResult:
    ok: bool
    message: str
    outputs: list[str]


# --------------------------------------------------------------- HTML
class _TextExtractor(HTMLParser):
    _BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.buffer: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        if tag in self._BLOCK:
            self.buffer.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self._skip:
            self._skip -= 1
        if tag in self._BLOCK:
            self.buffer.append("\n")

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.buffer.append(data)

    def text(self) -> str:
        raw = "".join(self.buffer)
        raw = re.sub(r"[ \t\u00a0]+", " ", raw)
        raw = re.sub(r" *\n *", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip() + "\n"


def html_to_text(markup: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(markup)
        parser.close()
        return parser.text()
    except Exception:                                  # noqa: BLE001 - HTML 千奇百怪
        text = re.sub(r"<[^>]+>", "", markup)
        return html.unescape(text)


def convert_html(path: str) -> ConvertResult:
    raw = open(path, "rb").read()
    for codec in ("utf-8", "gb18030", "utf-16"):
        try:
            markup = raw.decode(codec)
            break
        except UnicodeDecodeError:
            continue
    else:
        markup = raw.decode("gb18030", errors="replace")
    text = html_to_text(markup)
    out = _out_path(path, ".txt")
    enc.save_text(out, text, "gb18030")
    return ConvertResult(True, "htm→txt 转换完成！", [out])


# --------------------------------------------------------------- EPUB
def _epub_spine(zf: zipfile.ZipFile) -> list[str]:
    names = zf.namelist()
    opf = next((n for n in names if n.lower().endswith(".opf")), None)
    if opf is None:
        return [n for n in names if n.lower().endswith((".html", ".htm", ".xhtml"))]
    base = os.path.dirname(opf)
    data = zf.read(opf).decode("utf-8", errors="ignore")
    manifest = dict(re.findall(r'<item[^>]*id="([^"]+)"[^>]*href="([^"]+)"', data))
    manifest.update({k: v for v, k in re.findall(r'<item[^>]*href="([^"]+)"[^>]*id="([^"]+)"', data)})
    order = re.findall(r'<itemref[^>]*idref="([^"]+)"', data)
    files = [os.path.join(base, manifest[i]).replace("\\", "/") for i in order if i in manifest]
    return [f for f in files if f in names] or [n for n in names if n.lower().endswith((".html", ".htm", ".xhtml"))]


def convert_epub(path: str) -> ConvertResult:
    if not zipfile.is_zipfile(path):
        return ConvertResult(False, "文件不是有效的 EPUB（ZIP）结构。", [])
    with zipfile.ZipFile(path) as zf:
        parts: list[str] = []
        for name in _epub_spine(zf):
            try:
                markup = zf.read(name).decode("utf-8", errors="ignore")
            except KeyError:
                continue
            body = html_to_text(markup).strip()
            if body:
                parts.append(body)
    text = "\n\n".join(parts) + "\n"
    out = _out_path(path, ".txt")
    enc.save_text(out, text, "gb18030")
    return ConvertResult(True, "epub→txt 转换完成！", [out])


# --------------------------------------------------------------- DOCX
def convert_docx(path: str) -> ConvertResult:
    if not zipfile.is_zipfile(path):
        return ConvertResult(False, "这不是 DOCX 文件（.doc 旧格式请先用 Word 另存为 .docx）。", [])
    with zipfile.ZipFile(path) as zf:
        try:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        except KeyError:
            return ConvertResult(False, "DOCX 中找不到 word/document.xml。", [])
    xml = xml.replace("</w:p>", "\n")
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    out = _out_path(path, ".txt")
    enc.save_text(out, text, "gb18030")
    return ConvertResult(True, "doc→txt 转换完成！", [out])


# --------------------------------------------------------------- PalmDoc / MOBI
def _palmdoc_decompress(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        i += 1
        if b == 0:
            out.append(0)
        elif b <= 8:
            out += data[i:i + b]
            i += b
        elif b <= 0x7F:
            out.append(b)
        elif b <= 0xBF:
            if i >= n:
                break
            b2 = data[i]
            i += 1
            pair = (b << 8) | b2
            dist = (pair >> 3) & 0x07FF
            length = (pair & 0x07) + 3
            if dist == 0 or dist > len(out):
                continue
            for _ in range(length):
                out.append(out[-dist])
        else:
            out.append(0x20)
            out.append(b ^ 0x80)
    return bytes(out)


def convert_pdb(path: str) -> ConvertResult:
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 78:
        return ConvertResult(False, "文件太小，不是有效的 PDB/PRC。", [])
    count = struct.unpack_from(">H", data, 76)[0]
    if count <= 1:
        return ConvertResult(False, "PDB 记录数为 0，无法解析。", [])
    offsets = [struct.unpack_from(">I", data, 78 + i * 8)[0] for i in range(count)]
    offsets.append(len(data))
    rec0 = data[offsets[0]:offsets[1]]
    if len(rec0) < 16:
        return ConvertResult(False, "PDB 头部不完整。", [])
    compression, _, text_len, rec_count, _, encryption = struct.unpack_from(">HHIHHI", rec0, 0)
    if encryption:
        return ConvertResult(False, "该文件带 DRM 加密，无法转换。", [])
    if compression not in (1, 2):
        return ConvertResult(False, "该 MOBI 使用 HUFF/CDIC 压缩，当前版本不支持。", [])
    chunks: list[bytes] = []
    for i in range(1, min(rec_count + 1, count)):
        rec = data[offsets[i]:offsets[i + 1]]
        chunks.append(rec if compression == 1 else _palmdoc_decompress(rec))
    raw = b"".join(chunks)[:text_len]
    for codec in ("utf-8", "gb18030", "big5"):
        try:
            text = raw.decode(codec)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("gb18030", errors="replace")
    text = text.replace("\r\n", "\n").strip() + "\n"
    out = _out_path(path, ".txt")
    enc.save_text(out, text, "gb18030")
    return ConvertResult(True, "pdb→txt 转换完成！", [out])


# --------------------------------------------------------------- JAR
def convert_jar(path: str) -> ConvertResult:
    if not zipfile.is_zipfile(path):
        return ConvertResult(False, "不是有效的 JAR（ZIP）文件。", [])
    with zipfile.ZipFile(path) as zf:
        entries = [n for n in zf.namelist() if n.lower().endswith((".txt", ".html", ".htm"))]
        if not entries:
            entries = [n for n in zf.namelist() if not n.endswith("/")][:50]
        parts: list[str] = []
        for name in entries:
            raw = zf.read(name)
            for codec in ("utf-8", "gb18030"):
                try:
                    body = raw.decode(codec)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                continue
            if name.lower().endswith((".html", ".htm")):
                body = html_to_text(body)
            parts.append(body.strip())
    text = "\n\n".join(p for p in parts if p) + "\n"
    out = _out_path(path, ".txt")
    enc.save_text(out, text, "gb18030")
    return ConvertResult(True, "jar→txt 转换完成！", [out])


# --------------------------------------------------------------- CHM
def convert_chm(path: str) -> ConvertResult:
    out_dir = os.path.splitext(path)[0] + "_htm"
    os.makedirs(out_dir, exist_ok=True)
    try:
        proc = subprocess.run(["hh.exe", "-decompile", out_dir, path],
                              capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ConvertResult(False, f"调用 hh.exe 失败：{exc}", [])
    files = [os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.lower().endswith((".htm", ".html"))]
    msg = "chm→htm 转换完成！" if files else "解包完成，但没有找到 htm 文件（返回码 %d）。" % proc.returncode
    return ConvertResult(bool(files), msg, files[:200])


# --------------------------------------------------------------- RTF
def convert_rtf(path: str) -> ConvertResult:
    raw = open(path, "rb").read().decode("latin-1")
    text = raw
    text = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), text)
    text = re.sub(r"\\par[d]?", "\n", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = text.replace("{", "").replace("}", "")
    try:
        text = text.encode("latin-1").decode("gb18030", errors="ignore")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    out = _out_path(path, ".txt")
    enc.save_text(out, text, "gb18030")
    return ConvertResult(True, "rtf→txt 转换完成！", [out])


# --------------------------------------------------------------- 编码转换
def convert_encoding(path: str, target: str = "utf-8",
                     newline: str | None = None) -> ConvertResult:
    doc = enc.read_text(path)
    enc.save_text(path, doc.text, target, newline or doc.newline, keep_bom=target != "gb18030")
    return ConvertResult(True, f"已转换为 {enc.ENCODING_LABELS.get(target, target)}。", [path])


def _out_path(path: str, suffix: str) -> str:
    base, _ = os.path.splitext(path)
    candidate = base + suffix
    if os.path.abspath(candidate) == os.path.abspath(path):
        candidate = base + "(1)" + suffix
    return candidate


# --------------------------------------------------------------- 注册表
CONVERTERS: dict[str, tuple[tuple[str, ...], str, object]] = {
    "Html2Txt": ((".html", ".htm", ".xhtml"), "HTML → 纯文本", convert_html),
    "ePub2txt": ((".epub",), "EPUB → 纯文本", convert_epub),
    "Doc2txt": ((".docx",), "Word(docx) → 纯文本", convert_docx),
    "Pdb2txt": ((".pdb", ".prc"), "PDB/PRC → 纯文本", convert_pdb),
    "Mobi2txt": ((".mobi", ".azw", ".azw3"), "MOBI/AZW → 纯文本", convert_pdb),
    "Jar2txt": ((".jar",), "JAR 电子书 → 纯文本", convert_jar),
    "Chm2htm": ((".chm",), "CHM → HTML", convert_chm),
    "Rtf2txt": ((".rtf",), "RTF → 纯文本", convert_rtf),
}

UNSUPPORTED: dict[str, str] = {
    "Umd2txt": "UMD 需要专用解析库，当前版本暂不支持。",
    "Txt2umd": "UMD 打包需要专用库，当前版本暂不支持。",
    "Txt2jar": "JAR 打包需要专用库，当前版本暂不支持。",
    "Txt2pdf": "PDF 生成需要额外字体与排版库，当前版本暂不支持。",
    "Pdf2txt": "PDF 文本抽取需要 PDF 解析库，当前版本暂不支持。",
    "Exe2htm": "EXE 电子书解包依赖特定壳结构，当前版本暂不支持。",
    "Hlp2Rtf": "HLP 反编译依赖系统工具，当前版本暂不支持。",
}


def supported_suffixes() -> str:
    exts: list[str] = []
    for suffixes, _, _ in CONVERTERS.values():
        exts.extend(suffixes)
    return ";".join("*" + e for e in dict.fromkeys(exts))


def convert(path: str, name: str) -> ConvertResult:
    item = CONVERTERS.get(name)
    if item is None:
        return ConvertResult(False, UNSUPPORTED.get(name, "未知的转换类型。"), [])
    _, _, func = item
    try:
        return func(path)
    except Exception as exc:                            # noqa: BLE001
        return ConvertResult(False, f"转换失败：{exc}", [])


def convert_many(paths: list[str], name: str) -> ConvertResult:
    outputs: list[str] = []
    failed: list[str] = []
    for path in paths:
        result = convert(path, name)
        outputs.extend(result.outputs)
        if not result.ok:
            failed.append(f"{os.path.basename(path)}：{result.message}")
    if outputs and not failed:
        return ConvertResult(True, "批文件转换完成!", outputs)
    if outputs:
        return ConvertResult(True, f"完成 {len(outputs)} 个文件，{len(failed)} 个失败：" + "；".join(failed[:3]), outputs)
    return ConvertResult(False, "；".join(failed[:5]) or "没有可转换的文件。", [])


__all__ = ["ConvertResult", "CONVERTERS", "UNSUPPORTED", "convert", "convert_many",
           "convert_encoding", "html_to_text", "supported_suffixes"]
