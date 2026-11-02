"""关于框文案：从 ``ABOUT.md`` 读，占位符替换后渲染成 HTML（规范 §八）。

**为什么文案不写在代码里**：规范 §八 要求「文案写在 Markdown 里，不写进代码」——
改一句介绍不用动 Python、也不用重算窗口高度。历史教训是同一段文案在 4 处
字符串数组里各写一份，改漏一处就前后不一致。

md 格式约定（与 ComicConverter 的 ``ABOUT.md`` 同一套）：

* ``## **{NAME}** **{VERSION}**`` —— 标题行，替换后去掉 ``**``，
  末尾版本号自动上强调色；
* ``**小节**`` —— 单独成段（下一行是列表时）；
  下一行是普通行时**合并同段**（中间隔一个空行也照样合并，「快捷键」就是这种）；
* ``- `` 开头 —— 列表条目，圆点用强调色、悬挂缩进；
* 普通行按空行分块；块内含 ``© `` 的行自动降为 11px 灰字页脚；
* 标题后第一块是副标题（12px ``#5C5C5C``）。

**不要发明私有标记**（如 ``<!--footer-->``）：页脚靠 ``©`` 约定识别，
这样同一份 md 换成 WPF 渲染器也读得懂。
"""

from __future__ import annotations

import html
import os
import sys

from .version import APP_NAME, APP_SUBTITLE, APP_VERSION, AUTHOR

#: md 文件名（随包分发到 exe 的 app/data 下）
MD_NAME = "ABOUT.md"

#: 版式数值（规范 §八：标题 19 / 正文 12 / 页脚 11）
TITLE_PX = 19
BODY_PX = 12
FOOTER_PX = 11


def md_path() -> str | None:
    """按「打包目录 → 仓库 → exe 同目录」的顺序找 ABOUT.md。"""
    roots: list[str] = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        roots.append(os.path.join(base, "app", "data"))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    roots.append(os.path.join(here, "data"))
    if getattr(sys, "frozen", False):
        roots.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "app", "data"))
    for root in roots:
        path = os.path.join(root, MD_NAME)
        if os.path.isfile(path):
            return path
    return None


def read_md() -> str:
    """读 md 原文；读不到返回空串（由调用方退回最小文案，绝不让窗口空白）。"""
    path = md_path()
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def placeholders() -> dict[str, str]:
    """md 里可用的占位符 —— 版本号/作者一律走这里，不写进 md 字面量。"""
    return {
        "{NAME}": APP_NAME,
        "{VERSION}": APP_VERSION,
        "{TAGLINE}": APP_SUBTITLE,
        "{AUTHOR}": AUTHOR,
    }


def _substitute(text: str) -> str:
    for key, value in placeholders().items():
        text = text.replace(key, value)
    return text


def _inline(text: str) -> str:
    """行内 ``**粗体**`` → ``<b>``，其余按 HTML 转义。"""
    out: list[str] = []
    bold = False
    for chunk in text.split("**"):
        if chunk:
            out.append("<b>" + html.escape(chunk) + "</b>" if bold else html.escape(chunk))
        bold = not bold
    return "".join(out)


def _blocks(text: str) -> list[list[str]]:
    """按空行切块，块内保留非空行。"""
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip():
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _is_list(block: list[str]) -> bool:
    return all(line.lstrip().startswith("- ") for line in block)


def _is_section(block: list[str]) -> bool:
    """``**小节**`` 单独一行。"""
    return (len(block) == 1 and block[0].startswith("**")
            and block[0].endswith("**") and block[0].count("**") == 2)


def render(text: str | None = None, accent: str = "") -> str:
    """把 md 渲成 QTextBrowser 能显示的 HTML。

    ``accent`` 由调用方传入强调色（theme.ACCENT）—— 这里不 import theme，
    免得 core 层依赖 ui 层、也免得纯逻辑测试要建 QApplication。
    """
    source = _substitute(read_md() if text is None else text)
    blocks = _blocks(source)
    if not blocks:
        # 兜底：md 丢了也给出标题与版本，不显示空窗口
        return (f'<p style="font-size:{TITLE_PX}px;font-weight:600;">'
                f'{html.escape(APP_NAME)} '
                f'<span style="color:{accent};">{html.escape(APP_VERSION)}</span></p>')

    parts: list[str] = []
    body_iter = list(blocks)
    subtitle_done = False

    while body_iter:
        block = body_iter.pop(0)
        first = block[0].lstrip()

        # ---- 标题行：## **名字** **版本**
        if first.startswith("## "):
            title = _substitute(first[3:].strip()).replace("**", " ").strip()
            # 末尾的版本号单独上强调色：最后一段与 VERSION 相等就包 <span>
            version = APP_VERSION
            if title.endswith(version):
                name = title[: -len(version)].rstrip()
                parts.append(
                    f'<p style="font-size:{TITLE_PX}px;font-weight:600;'
                    f'margin:0 0 2px 0;">{html.escape(name)} '
                    f'<span style="color:{accent};">{html.escape(version)}</span></p>')
            else:
                parts.append(f'<p style="font-size:{TITLE_PX}px;font-weight:600;'
                             f'margin:0 0 2px 0;">{html.escape(title)}</p>')
            continue

        # ---- 副标题：标题后的第一块
        if not subtitle_done and not _is_list(block) and not _is_section(block):
            subtitle_done = True
            parts.append(f'<p style="color:#5C5C5C;font-size:{BODY_PX}px;'
                         f'margin:0 0 4px 0;">{_inline(" ".join(block))}</p>')
            continue
        subtitle_done = True

        # ---- 列表
        if _is_list(block):
            for line in block:
                item = _inline(line.lstrip()[2:].strip())
                # 悬挂缩进：圆点距正文左边界 13px，回行与文字对齐
                parts.append(
                    f'<p style="margin:0 0 0 26px;text-indent:-13px;'
                    f'font-size:{BODY_PX}px;">'
                    f'<span style="color:{accent};">•</span>　{item}</p>')
            continue

        # ---- 小节标题：下一块不是列表就并进同一段（「快捷键」那种）
        if _is_section(block):
            head = "<b>" + html.escape(block[0].strip("*").strip()) + "</b>"
            merged: list[str] = []
            if body_iter and not _is_list(body_iter[0]) and not _is_section(body_iter[0]) \
                    and not body_iter[0][0].lstrip().startswith("## "):
                merged = body_iter.pop(0)
            lines = "<br>".join(_inline(x) for x in merged)
            body = f"{head}<br>{lines}" if lines else head
            parts.append(f'<p style="font-size:{BODY_PX}px;margin:12px 0 0 0;">{body}</p>')
            continue

        # ---- 普通段落；含 © 的降为页脚
        joined = _inline(" ".join(block)) if len(block) == 1 else \
            "<br>".join(_inline(x) for x in block)
        if "©" in " ".join(block):
            parts.append(f'<p style="color:#8A8A8A;font-size:{FOOTER_PX}px;'
                         f'margin:12px 0 0 0;">{joined}</p>')
        else:
            parts.append(f'<p style="font-size:{BODY_PX}px;margin:12px 0 0 0;">{joined}</p>')

    return "\n".join(parts)


__all__ = ["MD_NAME", "md_path", "read_md", "placeholders", "render"]
