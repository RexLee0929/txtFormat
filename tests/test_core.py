"""核心逻辑自测（不依赖 GUI）。

运行：``.venv/Scripts/python.exe tests/test_core.py``
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import adfilter, chapter, checkers, encoding as enc, formatter  # noqa: E402
from app.core import numcn, punct, regexlib, splitter, zhconv  # noqa: E402
from app.core.settings import Settings  # noqa: E402

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f"{name} {extra}")


def eq(name: str, got, want) -> None:
    check(name, got == want, f"\n   got ={got!r}\n   want={want!r}")


# ------------------------------------------------------------------ 编码
def test_encoding() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "a.txt")
        text = "第一行\n第二行\n"
        enc.save_text(path, text, "gb18030", "\r\n")
        raw = open(path, "rb").read()
        check("gbk 写出 CRLF", b"\r\n" in raw)
        doc = enc.read_text(path)
        eq("gbk 读回", doc.text, text)
        eq("编码识别", doc.encoding, "gb18030")

        enc.save_text(path, text, "utf-8", "\r\n", keep_bom=True)
        check("utf8 带 BOM", open(path, "rb").read().startswith(b"\xef\xbb\xbf"))
        eq("utf8 读回", enc.read_text(path).text, text)

        enc.save_text(path, text, "utf-16-le", "\n")
        eq("utf16 读回", enc.read_text(path).text, text)

        eq("无 BOM UTF8 检测", enc.detect_encoding("中文".encode("utf-8")), "utf-8")
        eq("GBK 检测", enc.detect_encoding("中文冲突".encode("gb18030")), "gb18030")


# ------------------------------------------------------------------ 数字
def test_numcn() -> None:
    cases = {1: "一", 10: "十", 11: "十一", 20: "二十", 32: "三十二", 100: "一百",
             101: "一百零一", 110: "一百一十", 1000: "一千", 1001: "一千零一",
             10000: "一万", 10001: "一万零一", 12345: "一万二千三百四十五",
             100000000: "一亿", 100010000: "一亿零一万"}
    for num, want in cases.items():
        eq(f"int_to_cn({num})", numcn.int_to_cn(num), want)
    for num in (1, 9, 10, 12, 32, 100, 108, 999, 1001, 10500, 12345):
        eq(f"roundtrip {num}", numcn.cn_to_int(numcn.int_to_cn(num)), num)
    eq("mixed 032", numcn.mixed_to_int("032"), 32)
    eq("mixed ０３２", numcn.mixed_to_int("０３２"), 32)
    eq("mixed 零三二", numcn.mixed_to_int("零三二"), 32)


# ------------------------------------------------------------------ 标点
def test_punct() -> None:
    eq("全角转换", punct.to_fullwidth_punct("他说,你好."), "他说，你好。")
    eq("保留小数点", punct.to_fullwidth_punct("圆周率是3.14,对吧"), "圆周率是3.14，对吧")
    eq("保留英文标点", punct.to_fullwidth_punct("Hello,world!"), "Hello,world!")
    eq("URL 冒号", punct.to_fullwidth_punct("见 http://a.com:80/x"), "见 http://a.com:80/x")
    eq("半角转换", punct.to_halfwidth_punct("他说，“你好”。"), '他说,"你好".')
    eq("中文空格", punct.strip_chinese_spaces("他 说 话"), "他说话")
    eq("行尾空格", punct.rstrip_lines("第一行  \n第二行　\n"), "第一行\n第二行\n")
    eq("非法组合", punct.fix_illegal_punct("好，，的。。"), "好，的……")
    eq("相向引号", punct.balance_quotes("“你好“"), "“你好”")


# ------------------------------------------------------------------ 正则库
def test_regexlib() -> None:
    lib = regexlib.RegexLibrary()
    check("内置条目数", len(lib.entries) > 50, f"got {len(lib.entries)}")
    bad = []
    for entry in lib.entries:
        if entry.kind != "regex":
            continue
        problem = regexlib.error_of(entry.pattern)
        if problem:
            bad.append(f"{entry.name}: {problem}")
    check("所有内置正则均可编译", not bad, "\n  " + "\n  ".join(bad))

    eq("$1 反引用", regexlib.convert_replacement(r"$1章 $2"), r"\g<1>章 \g<2>")
    text = "第1章 开始\n正文。\n"
    new, n = regexlib.replace_all(text, r"第([0-9]+)章", r"第$1章")
    eq("替换计数", n, 1)
    eq("替换结果", new, text)

    found = regexlib.find_all("abc你好123", r"[0-9]+")
    eq("查找数字", [m.text for m in found], ["123"])
    total, kinds = regexlib.count_matches("a1b2c3", r"[0-9]")
    eq("计数", (total, kinds), (3, 3))


# ------------------------------------------------------------------ 章节
def test_chapter() -> None:
    text = (
        "前言内容。\n\n"
        "第1章 开端\n他说。\n\n"
        "第2章 发展\n她说。\n\n"
        "第３章 高潮\n好啊。\n"
    )
    chapters = chapter.parse_chapters(text)
    eq("章节数", len(chapters), 3)
    eq("首章标题", chapters[0].title, "第1章 开端")
    eq("章号", [c.number for c in chapters], [1, 2, 3])

    fixed, count = chapter.normalize_titles(text, chapter.DEFAULT_FORMAT, "cn")
    check("规范化为中文", "第三章 高潮" in fixed, fixed)
    eq("规范化次数", count, 3)

    numbered, _ = chapter.renumber(text, chapter.DEFAULT_FORMAT, "num")
    check("重新编号", "第1章 开端" in numbered and "第3章 高潮" in numbered, numbered)

    parts = chapter.split_by_chapters(text)
    eq("分割数量", len(parts), 4)      # 含前言
    eq("前言标题", parts[0][0], "前言")


# ------------------------------------------------------------------ 格式整理
SAMPLE = (
    "　　他慢慢的说,这件事很奇怪。\n"
    "　　第二天早上,他醒了过来,发现自己躺在床上,身上盖着被子,窗外阳光明媚,鸟语花香,"
    "一切看起来都很正常,但是他心里总觉得有什么地方不太对劲,于是起身走到窗前\n"
    "　　向外望去。\n"
    "16K小说网 更新时间:2010-3-4 13:02:57 本章字数:4143\n"
    "　　少*妇站在门口。\n"
)


def test_formatter() -> None:
    st = Settings()
    st.para_spacing = "keep"
    st.indent_kind = "full"
    st.indent_count = 2
    result = formatter.format_text(SAMPLE, st)
    out = result.text
    check("标点转全角", "，" in out, out)
    check("删除广告行", "16K小说网" not in out, out)
    check("行首缩进", "　　他慢慢的说" in out, out)
    check("还原屏蔽码", "少妇站在门口" in out, out)
    check("硬回车合并", "于是起身走到窗前向外望去" in out, out)
    check("Unicode 码还原", formatter.convert_unicode_codes("&#29234;好")[0] == "\u7232好")
    check("Unicode 十六进制", formatter.convert_unicode_codes("&#x4e2d;&#25991;")[0] == "中文")

    st2 = Settings()
    st2.para_spacing = "none"
    out2 = formatter.format_text("第一段\n\n\n第二段\n", st2).text
    check("删除空行", "\n\n" not in out2.strip("\n"), repr(out2))

    check("章节行识别", formatter.is_chapter_line("　　第12章 标题"))
    check("非章节行", not formatter.is_chapter_line("　　他走了。"))


# ------------------------------------------------------------------ 检查器
def test_checkers() -> None:
    issues = checkers.check_typos("这件事必竟是他做的，按纳不住。")
    found = {i.text for i in issues}
    check("错别字检出", {"必竟", "按纳"} <= found, str(found))
    dedi = checkers.check_dedi("他慢慢的说：“走吧。”")
    check("的得地检出", any(i.suggestion == "地" for i in dedi), str([(i.text, i.suggestion) for i in dedi]))
    trad = checkers.check_traditional("我們說話")
    eq("繁体检出", len(trad), 3)
    check("引号不匹配", checkers.check_quotes("“你好\n世界”"))
    check("半个括号", checkers.check_brackets("他说（然后走了。"))
    check("标点问题", checkers.check_punct("好，，的"))


# ------------------------------------------------------------------ 广告
def test_adfilter() -> None:
    text = "正文内容。\n16K小说网 更新时间:2010 本章字数:100\n更多精彩。\n"
    frags = adfilter.scan(text, r"^.{0,60}更新时间.{1,40}本章字数.{0,20}$")
    eq("扫描广告", len(frags), 1)
    new, n = adfilter.apply_remove_list(text, frags)
    check("删除广告", "更新时间" not in new and "正文内容" in new, new)
    eq("删除次数", n, 1)


# ------------------------------------------------------------------ 分割合并
def test_splitter() -> None:
    text = "\n".join(f"第{i}行内容，长度还可以。" for i in range(1, 400))
    with tempfile.TemporaryDirectory() as tmp:
        res = splitter.split_by_size(text, 2, tmp, "part")
        check("按大小分割", len(res.files) >= 4, str(len(res.files)))
        eq("自然排序", splitter.natural_key("第10章.txt") < splitter.natural_key("第9章.txt"), False)

        joined, n = splitter.merge_files(res.files, os.path.join(tmp, "merged.txt"))
        eq("合并文件数", n, len(res.files))
        check("合并结果非空", os.path.getsize(joined) > 1000)

        sample = os.path.join(tmp, "第一章 开始.txt")
        open(sample, "w", encoding="utf-8").write("内容")
        r = splitter.rename_remove_text([sample], "第一章 ")
        eq("更名结果", os.path.basename(r.renamed[0][1]), "开始.txt")


# ------------------------------------------------------------------ 简繁
def test_zhconv() -> None:
    s = "我们说话的时候看见这本书"
    t = zhconv.to_traditional(s)
    check("简转繁", t != s and "說" in t, t)
    eq("繁转简", zhconv.to_simplified(t), s)


def main() -> int:
    for fn in (test_encoding, test_numcn, test_punct, test_regexlib, test_chapter,
               test_formatter, test_checkers, test_adfilter, test_splitter, test_zhconv):
        try:
            fn()
        except Exception as exc:                        # noqa: BLE001
            import traceback
            FAILURES.append(f"{fn.__name__} 异常: {exc}\n{traceback.format_exc()}")
            globals()["FAIL"] += 1
    print(f"\n通过 {PASS} 项，失败 {FAIL} 项")
    if FAILURES:
        print("\n失败详情：")
        for f in FAILURES:
            print(" -", f)
        return 1
    print("核心逻辑自测全部通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
