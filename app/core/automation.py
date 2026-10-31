"""自动化任务：把程序已有的文本处理功能按顺序批量调用。

设计约束（用户明确要求）：

* 任务 = 有序步骤列表，保存在 config.json 的 ``automations`` 字段里；
* **每个步骤单独携带自己的选项**：同一个功能可以出现多次、配置各不相同
  （例：先做一次格式整理 → 查找替换 → 再做一次不同设置的格式整理）；
* 步骤执行时**只读**步骤自带的配置，绝不读写程序当前的 Settings ——
  格式整理步骤用的是由步骤配置重建的独立 Settings 副本；
* 步骤全部是「文本进、文本出」的纯转换：不写任何文件（remove.txt 只读），
  也不打开对话框，因此可以在后台线程整批执行。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from . import adfilter, formatter, punct, regexlib, zhconv
from .settings import Settings


@dataclass
class RunContext:
    """一次自动化执行的公共环境（目前只有文档所在目录，供 remove.txt 用）。"""

    base_dir: str = ""


# ---------------------------------------------------------------- 步骤规格
@dataclass(frozen=True)
class StepSpec:
    """一种可加入自动化任务的功能。

    ``run(text, config, ctx) -> (新文本, 一句话结果说明)``；
    ``summarize(config)`` 给编辑器列表用，把配置缩写成一行。
    """

    key: str
    label: str
    icon: str
    has_options: bool
    default_config: dict
    summarize: Callable[[dict], str]
    run: Callable[[str, dict, RunContext], tuple[str, str]]


# 格式整理步骤携带的选项字段（Settings 里「格式整理」相关的全部字段；
# recursive / sort_by_number 是文件列表行为，与文本处理无关，不带入）
FORMAT_FIELDS = (
    "punct_mode", "english_mode", "number_mode", "para_spacing",
    "indent_kind", "indent_count", "auto_hard_return", "hard_return_width",
    "has_ad", "split_by_period", "remove_spaces_in_text",
    "convert_unicode_code", "restore_screened", "restore_pinyin",
    "fix_punct_combo",
)

_PUNCT_LABEL = {"full": "全角", "half": "半角", "keep": "原样"}
_INDENT_LABEL = {"half": "半角空格", "full": "全角空格", "tab": "制表符", "none": "无"}


def _run_format(text: str, config: dict, _ctx: RunContext) -> tuple[str, str]:
    snapshot = Settings()
    for field_name in FORMAT_FIELDS:
        if field_name in config:
            setattr(snapshot, field_name, config[field_name])
    result = formatter.format_text(text, snapshot)
    if not result.changed:
        return result.text, "文档已是规范格式"
    stats = result.stats.as_text()
    return result.text, stats or "完成"


def _summarize_format(config: dict) -> str:
    parts = [f"标点{_PUNCT_LABEL.get(config.get('punct_mode'), '原样')}"]
    if config.get("indent_kind") in _INDENT_LABEL and config.get("indent_kind") != "none":
        parts.append(f"缩进{config.get('indent_count', 2)}{_INDENT_LABEL[config.get('indent_kind')]}")
    if config.get("para_spacing") == "blank":
        parts.append("段间空一行")
    if config.get("auto_hard_return"):
        parts.append("处理硬回车")
    return " · ".join(parts)


def _run_replace(text: str, config: dict, _ctx: RunContext) -> tuple[str, str]:
    pattern = str(config.get("pattern") or "")
    if not pattern:
        return text, "未填写查找内容，已跳过"
    replacement = str(config.get("replacement") or "")
    ignore_case = bool(config.get("ignore_case", False))
    if not config.get("use_regex", True):
        pattern = re.escape(pattern)
    new_text, count = regexlib.replace_all(text, pattern, replacement, ignore_case)
    return new_text, f"替换 {count} 处" if count else "没有匹配内容"


def _summarize_replace(config: dict) -> str:
    pattern = (str(config.get("pattern") or "").replace("\n", " "))[:20]
    repl = (str(config.get("replacement") or "").replace("\n", " "))[:14]
    mark = "" if config.get("use_regex", True) else "（非正则）"
    return f"{pattern} → {repl or '删除'}{mark}"


def _run_zhconv(text: str, config: dict, _ctx: RunContext) -> tuple[str, str]:
    mode = config.get("mode", "t2s")
    label = dict((m, l.split(" ")[0]) for l, m in zhconv.CONVERT_MODES).get(mode, "转换")
    return zhconv.convert(text, mode), label


def _summarize_zhconv(config: dict) -> str:
    return dict((m, l.split(" ")[0]) for l, m in zhconv.CONVERT_MODES).get(
        config.get("mode", "t2s"), "繁转简")


def _run_rstrip(text: str, _config: dict, _ctx: RunContext) -> tuple[str, str]:
    new_text = punct.rstrip_lines(text)
    return new_text, "完成" if new_text != text else "没有行尾空格"


def _run_quotes(text: str, _config: dict, _ctx: RunContext) -> tuple[str, str]:
    new_text = punct.balance_quotes(text)
    return new_text, "完成" if new_text != text else "引号已配对"


def _run_adremove(text: str, _config: dict, ctx: RunContext) -> tuple[str, str]:
    path = adfilter.default_remove_path(ctx.base_dir) if ctx.base_dir else ""
    fragments = adfilter.read_remove_list(path) if path else []
    if not fragments:
        return text, "未找到 remove.txt，已跳过"
    new_text, count = adfilter.apply_remove_list(text, fragments)
    return new_text, f"按 remove.txt 删除 {count} 处" if count else "没有可删除的内容"


def _steps() -> list[StepSpec]:
    return [
        StepSpec("format", "格式整理", "format", True,
                 {name: getattr(Settings(), name) for name in FORMAT_FIELDS},
                 _summarize_format, _run_format),
        StepSpec("replace", "查找替换", "replace", True,
                 {"pattern": "", "replacement": "", "use_regex": True, "ignore_case": False},
                 _summarize_replace, _run_replace),
        StepSpec("zhconv", "简繁转换", "convert", True,
                 {"mode": "t2s"}, _summarize_zhconv, _run_zhconv),
        StepSpec("rstrip", "去除行尾空格", "clean", False, {}, lambda _c: "每行行尾空格/制表符", _run_rstrip),
        StepSpec("quotes", "首尾引号规范化", "check", False, {}, lambda _c: "同向引号改为相向", _run_quotes),
        StepSpec("adremove", "按 remove.txt 删除广告", "clean", False, {},
                 lambda _c: "读取文档目录下的 remove.txt", _run_adremove),
    ]


#: key -> 规格（执行与编辑共用）
STEP_TYPES: dict[str, StepSpec] = {spec.key: spec for spec in _steps()}
#: 新建步骤时的排列顺序
STEP_ORDER: list[str] = [spec.key for spec in _steps()]


# ---------------------------------------------------------------- 执行
def run_automation(text: str, steps: list[dict], base_dir: str = "") -> tuple[str, list[str]]:
    """按顺序执行一个任务的全部步骤，返回 (最终文本, 每步的结果说明)。

    单个步骤抛异常只记入该步的说明、不中断后续步骤 —— 批量任务里
    一步的正则写错不该让后面几步全部白配。
    """
    ctx = RunContext(base_dir=base_dir)
    notes: list[str] = []
    for step in steps:
        spec = STEP_TYPES.get(str(step.get("type", "")))
        if spec is None:
            notes.append("未知步骤，已跳过")
            continue
        config = step.get("config")
        config = config if isinstance(config, dict) else dict(spec.default_config)
        try:
            text, note = spec.run(text, config, ctx)
            notes.append(f"{spec.label}：{note}")
        except re.error as exc:
            notes.append(f"{spec.label}：正则有误（{exc}），已跳过")
        except Exception as exc:                        # noqa: BLE001 - 同上
            notes.append(f"{spec.label}：执行失败（{exc}）")
    return text, notes


# ---------------------------------------------------------------- 持久化
def normalize_automations(data: object) -> list[dict]:
    """把 config.json 里读到的 automations 清洗成合法结构。

    坏项（不是字典、没有名字、步骤类型不存在）直接丢弃，不让手改坏
    的配置把界面/执行搞崩。名字重复的保留先出现的那个。
    """
    if not isinstance(data, list):
        return []
    result: list[dict] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip() or name in seen:
            continue
        raw_steps = item.get("steps")
        steps: list[dict] = []
        if isinstance(raw_steps, list):
            for step in raw_steps:
                if not isinstance(step, dict) or step.get("type") not in STEP_TYPES:
                    continue
                config = step.get("config")
                steps.append({
                    "type": step["type"],
                    "config": config if isinstance(config, dict) else {},
                })
        result.append({"name": name, "steps": steps})
        seen.add(name)
    return result


__all__ = ["FORMAT_FIELDS", "STEP_ORDER", "STEP_TYPES", "RunContext", "StepSpec",
           "normalize_automations", "run_automation"]
