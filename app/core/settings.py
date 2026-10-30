"""选项设置（对应原程序“格式整理选项 / 选项设置”）。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields

from .paths import root_dir


def _legacy_path() -> str:
    """旧版把设置写在 %APPDATA%\\txtFormat\\settings.json，只读向后兼容。"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "txtFormat", "settings.json")


# 设置与程序放在一起（规范 §十：exe 同目录 = config.json）。
SETTINGS_PATH = os.path.join(root_dir(), "config.json")


@dataclass
class Settings:
    # ---- 格式整理 ----
    punct_mode: str = "full"          # full / half / keep —— 标点符号处理
    english_mode: str = "half"        # full / half / keep —— 英文字符处理
    number_mode: str = "keep"         # full / half / keep —— 数值处理
    para_spacing: str = "keep"        # blank / none / keep —— 段落间隔行
    indent_kind: str = "full"         # half / full / tab / none —— 行首缩进
    indent_count: int = 2             # 缩进个数
    auto_hard_return: bool = True     # 自动处理硬回车
    hard_return_width: int = 30       # 去掉硬回车时的行宽
    has_ad: bool = True               # 文档中包含有广告
    split_by_period: bool = False     # 以句号为段落标记重新分段
    remove_spaces_in_text: bool = True  # 除去非标题行中的空格
    convert_unicode_code: bool = True   # 把 &#xxxx; 转成汉字
    restore_screened: bool = True       # 还原屏蔽码
    restore_pinyin: bool = True         # 还原拼音
    fix_punct_combo: bool = True        # 标点组合规范化
    check_level: int = 1              # 错别字/的得地 搜索等级 1-3

    # ---- 文件列表 ----
    sort_by_number: bool = True       # 按文件名中的数字排序
    recursive: bool = False           # 处理子目录中的文件

    # ---- 编辑器 ----
    font_family: str = "Microsoft YaHei UI"
    font_size: int = 12
    line_height_percent: int = 160
    show_statusbar: bool = True
    word_wrap: bool = True
    auto_scroll: bool = False
    show_reading_guide: bool = False  # 显示水线
    save_encoding: str = "gb18030"
    newline: str = "\r\n"

    # ---- 路径 ----
    last_dir: str = ""
    last_files: list[str] = field(default_factory=list)

    # ---- 内部 ----
    settings_version: int = 2

    # ------------------------------------------------------------ 持久化
    @classmethod
    def ensure_default(cls, path: str | None = None) -> str:
        """首次运行时落盘一份默认 config.json（规范 §三.2）。

        安装器的「检测到本地已有配置」只认安装目录里的 config.json；如果程序只在
        用户改设置时才写文件，全新装完、从没动过设置的用户重装时就永远检测不到配置，
        「覆盖现有配置」「保留配置文件」全都无从谈起。所以启动时就把配置写出来，
        让「已有配置」成为常态而不是例外。

        已有 config.json 就原样不动；新位置还没有但旧位置（%APPDATA%）有设置时，
        先把旧设置迁过来，避免用户丢掉自己调过的选项。
        """
        path = path or SETTINGS_PATH
        if os.path.exists(path):
            return path
        try:
            legacy = _legacy_path()
            if os.path.exists(legacy):
                cls.load(legacy).save(path)          # 迁移旧设置，不丢用户改动
            else:
                cls().save(path)                     # 写一份默认配置
        except OSError:
            pass
        return path

    @classmethod
    def load(cls, path: str | None = None) -> "Settings":
        path = path or SETTINGS_PATH
        if not os.path.exists(path):
            # 新位置还没有配置时，回读旧版留在 %APPDATA% 的设置（只读，不搬文件）。
            legacy = _legacy_path()
            if os.path.exists(legacy):
                path = legacy
        obj = cls()
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                valid = {f.name for f in fields(cls)}
                for key, value in data.items():
                    if key in valid:
                        setattr(obj, key, value)
                # v1 的默认字号 11pt 偏小，升级时抬到 12pt（用户自己改过的不动）
                if data.get("settings_version", 1) < 2 and data.get("font_size") == 11:
                    obj.font_size = 12
            except (OSError, json.JSONDecodeError):
                pass
        return obj

    def save(self, path: str | None = None) -> None:
        path = path or SETTINGS_PATH
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(asdict(self), fh, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def reset_format_options(self) -> None:
        """“恢复默认设置”——只重置格式整理相关项。"""
        default = Settings()
        for name in ("punct_mode", "english_mode", "number_mode", "para_spacing",
                     "indent_kind", "indent_count", "auto_hard_return",
                     "hard_return_width", "has_ad", "split_by_period",
                     "remove_spaces_in_text", "convert_unicode_code",
                     "restore_screened", "restore_pinyin", "fix_punct_combo",
                     "check_level"):
            setattr(self, name, getattr(default, name))

    @property
    def indent_text(self) -> str:
        if self.indent_kind == "none":
            return ""
        if self.indent_kind == "tab":
            return "\t" * max(1, self.indent_count // 2 or 1)
        unit = "　" if self.indent_kind == "full" else " "
        return unit * self.indent_count


__all__ = ["Settings", "SETTINGS_PATH"]
