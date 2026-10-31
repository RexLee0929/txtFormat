"""文件分割 / 文件合并 / 批量更名。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from . import chapter as chapter_mod
from . import encoding as enc


@dataclass
class SplitResult:
    files: list[str]
    chapters: int = 0


def split_by_size(text: str, size_kb: int, out_dir: str, prefix: str,
                  encoding: str = "gb18030", newline: str = "\r\n") -> SplitResult:
    """按固定大小分割，尽量在行边界处断开。"""
    limit = max(1, size_kb) * 1024
    lines = text.split("\n")
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for line in lines:
        raw = len(line.encode(encoding, errors="ignore")) + 2
        if size + raw > limit and buf:
            chunks.append("\n".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += raw
    if buf:
        chunks.append("\n".join(buf))

    os.makedirs(out_dir, exist_ok=True)
    files: list[str] = []
    stem = prefix or "part"
    for i, chunk in enumerate(chunks, 1):
        path = chapter_mod.unique_path(out_dir, f"{stem}_{i:03d}")
        enc.save_text(path, chunk, encoding, newline)
        files.append(path)
    return SplitResult(files)


def split_by_chapter(text: str, pattern: str, out_dir: str, prefix: str,
                     encoding: str = "gb18030", newline: str = "\r\n",
                     use_title_as_name: bool = True) -> SplitResult:
    parts = chapter_mod.split_by_chapters(text, pattern)
    os.makedirs(out_dir, exist_ok=True)
    files: list[str] = []
    for i, (title, body) in enumerate(parts, 1):
        stem = chapter_mod.safe_filename(title) if use_title_as_name else f"{prefix or 'chapter'}_{i:04d}"
        if prefix and use_title_as_name:
            stem = chapter_mod.safe_filename(f"{prefix}_{title}")
        path = chapter_mod.unique_path(out_dir, stem)
        enc.save_text(path, body + "\n", encoding, newline)
        files.append(path)
    return SplitResult(files, len(parts))


def merge_files(paths: list[str], out_path: str, add_filename_as_chapter: bool = False,
                chapter_mode: str = "cn", encoding: str = "gb18030",
                newline: str = "\r\n", delete_sources: bool = False) -> tuple[str, int]:
    """合并多个文件；可选把文件名作为章节标题插入。"""
    blocks: list[str] = []
    for path in paths:
        try:
            doc = enc.read_text(path)
        except OSError:
            continue
        body = doc.text.rstrip("\n")
        if add_filename_as_chapter:
            title = os.path.splitext(os.path.basename(path))[0]
            title = chapter_mod.make_chapter_title(len(blocks) + 1, title, chapter_mode)
            body = f"{title}\n\n{body}"
        blocks.append(body)
    text = "\n\n".join(blocks)
    if not text.endswith("\n"):
        text += "\n"
    enc.save_text(out_path, text, encoding, newline)
    if delete_sources:
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                pass
    return out_path, len(blocks)


# ------------------------------------------------------------------ 更名
@dataclass
class RenameResult:
    renamed: list[tuple[str, str]]
    skipped: list[str]


def natural_key(name: str) -> tuple:
    """按文件名中的数字排序。"""
    parts = re.split(r"(\d+)", name)
    return tuple(int(p) if p.isdigit() else p.lower() for p in parts)


def rename_strip_prefix(paths: list[str], count: int) -> RenameResult:
    return _rename(paths, lambda stem, ext: stem[count:] if len(stem) > count else stem)


def rename_remove_text(paths: list[str], needle: str) -> RenameResult:
    return _rename(paths, lambda stem, ext: stem.replace(needle, ""))


def rename_cut_after(paths: list[str], marker: str) -> RenameResult:
    """删除某字符之后的内容（保留该字符）。"""
    def fn(stem: str, ext: str) -> str:
        idx = stem.find(marker)
        return stem[: idx + len(marker)] if idx >= 0 else stem
    return _rename(paths, fn)


def rename_cut_before(paths: list[str], marker: str) -> RenameResult:
    """删除某字符之前的内容（含该字符）。"""
    def fn(stem: str, ext: str) -> str:
        idx = stem.find(marker)
        return stem[idx + len(marker):] if idx >= 0 else stem
    return _rename(paths, fn)


def _rename(paths: list[str], transform) -> RenameResult:
    renamed: list[tuple[str, str]] = []
    skipped: list[str] = []
    for path in paths:
        directory, filename = os.path.split(path)
        stem, ext = os.path.splitext(filename)
        new_stem = transform(stem, ext).strip()
        if not new_stem or new_stem == stem:
            skipped.append(path)
            continue
        target = os.path.join(directory, new_stem + ext)
        target = chapter_mod.unique_path(directory, new_stem, ext)
        try:
            os.rename(path, target)
            renamed.append((path, target))
        except OSError:
            skipped.append(path)
    return RenameResult(renamed, skipped)


__all__ = [
    "SplitResult", "RenameResult", "split_by_size", "split_by_chapter",
    "merge_files", "natural_key", "rename_strip_prefix", "rename_remove_text",
    "rename_cut_after", "rename_cut_before",
]
