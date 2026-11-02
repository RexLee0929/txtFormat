"""菜单树：**纯数据**（规范 §一 / §五.2）。

这里只有文本、命令 id、快捷键提示、图标名 —— 不含任何 Qt 类型、不绑任何槽。
建树在 :mod:`app.ui.main_window`（``_build_menus``），分发在一个 switch 式的方法里
（``MainWindow._dispatch``）。好处有三个：

* 加功能 = 表里加一条 + 分发器加一个分支，两处都在代码里，一眼看完；
* 菜单结构可以被**程序**验证（§十 四断言：一级菜单 ≥2、每栏非空且至少一项可用、
  存在「帮助」、能定位到 about 命令），不用靠人眼看；
* 外观（白色圆角卡片、图标列、快捷键灰）与本表彻底解耦，换渲染器不用动数据。

助记符写在文本里（``文件(&F)``），Qt 自己处理成「文件(F)」+ 下划线。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    """一个菜单项。``text == "-"`` 表示分隔线。"""

    text: str
    cmd: str = ""                     # 命令 id，交给 MainWindow._dispatch
    args: tuple = ()                  # 命令参数（同一命令的不同用法）
    gesture: str = ""                 # 右侧快捷键提示（注册另做，避免双绑）
    icon: str = ""                    # icons.PATHS 的键；空 = 占位不画
    checkable: bool = False
    checked: bool = False
    enabled: bool = True
    attr: str = ""                    # 建出的 QAction 挂到 MainWindow 的哪个属性
    submenu: tuple["Item", ...] = ()


SEP = Item("-")


@dataclass(frozen=True)
class Group:
    """一级菜单（菜单栏上的一栏）。"""

    title: str
    items: tuple[Item, ...] = field(default_factory=tuple)


#: 帮助菜单里「关于」的命令 id —— §十 断言要能定位到它
ABOUT_CMD = "help.about"


MENUS: tuple[Group, ...] = (
    Group("文件(&F)", (
        Item("新建", "file.new", gesture="Ctrl+N", icon="new"),
        Item("打开…", "file.open", gesture="Ctrl+O", icon="open"),
        Item("保存", "file.save", gesture="Ctrl+S", icon="save"),
        Item("另存为…", "file.save_as", gesture="Ctrl+Shift+S", icon="save-as"),
        SEP,
        Item("打开所在文件夹", "file.reveal", icon="folder"),
        SEP,
        Item("还原为打开时的内容", "file.revert", icon="undo",
             enabled=False, attr="act_revert"),
        SEP,
        Item("退出", "file.quit", gesture="Esc", icon="close"),
    )),
    Group("编辑(&E)", (
        Item("撤消", "edit.undo", gesture="Ctrl+Z", icon="undo"),
        Item("恢复", "edit.redo", gesture="Ctrl+Shift+Z", icon="redo"),
        SEP,
        Item("剪切", "edit.cut", gesture="Ctrl+X", icon="outdent"),
        Item("复制", "edit.copy", gesture="Ctrl+C", icon="copy"),
        Item("粘贴", "edit.paste", gesture="Ctrl+V", icon="insert"),
        Item("全选", "edit.select_all", gesture="Ctrl+A", icon="check"),
        SEP,
        Item("转到…", "edit.goto", gesture="Ctrl+G", icon="goto"),
        Item("向下查找下一个", "edit.find_next", args=(True,), gesture="F3", icon="next"),
        Item("向上查找上一个", "edit.find_prev", args=(False,), gesture="Shift+F3", icon="prev"),
        SEP,
        Item("插入", submenu=(
            Item("插入符号：“", "edit.insert_text", args=("“",), icon="insert"),
            Item("插入符号：……", "edit.insert_text", args=("……",), icon="insert"),
            Item("插入分隔线：※※※", "edit.insert_text", args=("※※※",), icon="insert"),
            Item("插入日期", "edit.insert_date", gesture="Ctrl+Shift+D", icon="file"),
            Item("插入文件名", "edit.insert_filename", icon="file"),
        )),
        Item("选定内容", submenu=(
            Item("制表符缩进", "edit.indent_tab", args=(1,), gesture="Tab", icon="indent"),
            Item("制表符反缩进", "edit.indent_tab", args=(-1,), gesture="Shift+Tab", icon="outdent"),
            Item("空格缩进", "edit.indent_spaces", args=(1,), icon="indent"),
            Item("空格反缩进", "edit.indent_spaces", args=(-1,), icon="outdent"),
            Item("去除行尾空格", "edit.strip_tail", icon="clean"),
            SEP,
            Item("转为大写", "edit.upper", icon="case"),
            Item("转为小写", "edit.lower", icon="case"),
            Item("首尾引号规范化", "edit.quotes", icon="format"),
        )),
    )),
    Group("查看(&V)", (
        Item("字体…", "view.font", icon="font"),
        Item("自动换行", "view.wrap", gesture="Ctrl+U", icon="wrap", checkable=True,
             attr="act_wrap"),
        Item("状态栏", "view.statusbar", icon="list", checkable=True, checked=True,
             attr="act_status"),
        Item("总在最前", "view.ontop", gesture="Ctrl+T", icon="pin", checkable=True,
             attr="act_onscreen"),
        SEP,
        Item("阅读模式", "view.reading", icon="read", checkable=True, attr="act_reading"),
        Item("自动卷屏", "view.autoscroll", icon="scroll", checkable=True, attr="act_scroll"),
        Item("显示水线", "view.guide", icon="rulers", checkable=True, attr="act_guide"),
        SEP,
        Item("统计选定（全部）内容", "view.stats", icon="stats"),
    )),
    Group("工具(&T)", (
        Item("格式整理", "tools.format", gesture="Ctrl+D", icon="format"),
        Item("格式整理选项…", "tools.format_options", icon="settings"),
        SEP,
        Item("广告检查及字符串计数", "tools.adcheck", gesture="Ctrl+Shift+A", icon="clean"),
        Item("自定义替换/删除", "tools.custom_replace", icon="replace"),
        SEP,
        Item("查找乱码", "tools.find_garbled", icon="search"),
        Item("修复选定乱码", "tools.fix_garbled", icon="search"),
        SEP,
        Item("文件分割 / 章节整理…", "tools.split", icon="split"),
        Item("文件更名 / 文件合并…", "tools.merge", icon="merge"),
        Item("重编码…", "tools.recode", icon="convert"),
        SEP,
        Item("以 ANSI 方式重新打开", "tools.reopen", args=("gb18030",), icon="refresh"),
        Item("以 UTF-8 方式重新打开", "tools.reopen", args=("utf-8",), icon="refresh"),
        Item("以 Unicode 方式重新打开", "tools.reopen", args=("utf-16-le",), icon="refresh"),
        SEP,
        Item("重新载入自定义正则", "tools.reload_regex", icon="refresh"),
    )),
    # 规范 §八：帮助菜单**只放两项** ——「关于」+ 作者邮箱（点了复制）；
    # 「重新载入自定义正则」是维护动作，归「工具」。
    Group("帮助(&H)", (
        Item("关于 txtFormat", ABOUT_CMD, icon="about"),
        Item("rexlee@rexleepro.com", "help.email", icon="mail"),
    )),
)


def all_items() -> list[Item]:
    """展平整棵菜单树（含子菜单），供结构断言与文档核对使用。"""
    out: list[Item] = []

    def walk(items: tuple[Item, ...]) -> None:
        for item in items:
            out.append(item)
            if item.submenu:
                walk(item.submenu)

    for group in MENUS:
        walk(group.items)
    return out


__all__ = ["Item", "Group", "SEP", "MENUS", "ABOUT_CMD", "all_items"]
