"""自动化面板与任务编辑器（右栏「替换规则」上方的那一块）。

交互设计（规范 §七：内联、少弹窗）：

* 面板只有两行 —— 标题行（新建/编辑/删除）+ 任务选择行（下拉框 + 运行）；
* 新建/编辑进同一个对话框：任务名 + 有序步骤列表，每个功能都可以加多次、
  各配各的选项（步骤配置保存在步骤里，运行时不碰程序自身的选项设置）；
* 删除走面板内的内联确认条，不弹模态框。
"""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QVBoxLayout, QWidget)

from ..core import automation, zhconv
from ..core.settings import Settings
from .dialogs import BaseDialog, OptionsDialog
from .panels import MultiLineEdit
from .widgets import (Caption, CommandButton, CompactComboBox, ConfirmBar,
                      IconButton, Menu, PrimaryButton, SectionLabel)


# ---------------------------------------------------------------- 面板
class AutomationPanel(QWidget):
    """自动化区：选择任务、一键执行、管理任务列表。"""

    #: 用户点了「运行」，参数是 {"name": str, "steps": [...]}
    run_requested = Signal(dict)

    def __init__(self, settings: Settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self._tasks: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(4)
        header.addWidget(SectionLabel("自动化"))
        header.addStretch(1)
        self.btn_new = IconButton("plus", "新建自动化", size=28)
        self.btn_edit = IconButton("edit", "编辑当前自动化", size=28)
        self.btn_del = IconButton("trash", "删除当前自动化", size=28)
        self.btn_new.clicked.connect(self._new)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        for btn in (self.btn_new, self.btn_edit, self.btn_del):
            header.addWidget(btn)
        layout.addLayout(header)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.combo = CompactComboBox(rows=8)
        self.combo.setMinimumHeight(30)
        self.combo.setToolTip("选择要执行的自动化任务")
        row.addWidget(self.combo, 1)
        self.btn_run = PrimaryButton("运行", "play")
        self.btn_run.setToolTip("按任务里的步骤顺序处理当前文档")
        self.btn_run.clicked.connect(self._run)
        row.addWidget(self.btn_run)
        layout.addLayout(row)

        # 删除确认条（规范 §七 ③：删除走内联确认，不弹模态框）
        self._delete_bar = ConfirmBar(self, "", "删除")
        self._delete_bar.confirmed.connect(self._do_delete)
        layout.addWidget(self._delete_bar)

        self.refresh()

    # ------------------------------------------------------------ 状态
    def refresh(self, select_name: str = "") -> None:
        """按 settings.automations 重建下拉框（顺带清洗坏数据）。"""
        tasks = automation.normalize_automations(self.settings.automations)
        self.settings.automations = tasks
        self._tasks = tasks
        self.combo.blockSignals(True)
        self.combo.clear()
        for task in tasks:
            self.combo.addItem(task["name"], task["name"])
        target = select_name or self.settings.last_automation
        names = [task["name"] for task in tasks]
        index = names.index(target) if target in names else (len(tasks) - 1 if tasks else -1)
        self.combo.setCurrentIndex(index)
        self.combo.blockSignals(False)
        has = bool(tasks)
        self.btn_run.setEnabled(has)
        self.btn_edit.setEnabled(has)
        self.btn_del.setEnabled(has)

    def current_task(self) -> dict | None:
        index = self.combo.currentIndex()
        if 0 <= index < len(self._tasks):
            return self._tasks[index]
        return None

    def _save(self) -> None:
        self.settings.save()

    # ------------------------------------------------------------ 动作
    def _run(self) -> None:
        task = self.current_task()
        if task is None:
            return
        self.settings.last_automation = task["name"]
        self.run_requested.emit(deepcopy(task))

    def _new(self) -> None:
        dialog = AutomationDialog(self.window(), None, [t["name"] for t in self._tasks])
        if dialog.exec() != BaseDialog.DialogCode.Accepted or not dialog.result_task:
            return
        self.settings.automations.append(dialog.result_task)
        self._save()
        self.refresh(select_name=dialog.result_task["name"])

    def _edit(self) -> None:
        task = self.current_task()
        if task is None:
            return
        others = [t["name"] for t in self._tasks if t is not task]
        dialog = AutomationDialog(self.window(), deepcopy(task), others)
        if dialog.exec() != BaseDialog.DialogCode.Accepted or not dialog.result_task:
            return
        index = self._tasks.index(task)
        self.settings.automations[index] = dialog.result_task
        self._save()
        self.refresh(select_name=dialog.result_task["name"])

    def _delete(self) -> None:
        task = self.current_task()
        if task is None:
            return
        self._delete_bar.show_for(f"删除自动化「{task['name']}」？", "删除")

    def _do_delete(self) -> None:
        task = self.current_task()
        if task is None:
            return
        self.settings.automations.remove(task)
        if self.settings.last_automation == task["name"]:
            self.settings.last_automation = ""
        self._save()
        self.refresh()


# ---------------------------------------------------------------- 任务编辑器
class AutomationDialog(BaseDialog):
    """新建 / 编辑一个自动化任务（任务名 + 有序步骤列表）。"""

    def __init__(self, parent: QWidget | None, task: dict | None,
                 taken_names: list[str] | None = None):
        super().__init__("编辑自动化" if task else "新建自动化", parent)
        self._taken = set(taken_names or ())
        self._original_name = task.get("name") if task else None
        self._steps: list[dict] = deepcopy(task.get("steps")) if task else []
        self.result_task: dict | None = None

        self.root.addWidget(SectionLabel("任务名称"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：老书入库清洗")
        if task:
            self.name_edit.setText(task.get("name", ""))
        self.root.addWidget(self.name_edit)

        self.root.addWidget(SectionLabel("执行步骤（自上而下依次执行）"))
        self.steps_list = QListWidget()
        self.steps_list.setToolTip("选中一步后可配置选项、调整顺序或移除")
        self.steps_list.setFixedHeight(168)
        self.root.addWidget(self.steps_list)

        row = QHBoxLayout()
        row.setSpacing(6)

        def add_btn(text: str, icon_name: str, slot, tip: str = "") -> CommandButton:
            btn = CommandButton(text, icon_name, kind="")
            if tip:
                btn.setToolTip(tip)
            btn.clicked.connect(slot)
            row.addWidget(btn)
            return btn

        self.add_btn = add_btn("添加功能", "plus", self._add_step, "把一个功能加到任务末尾")
        add_btn("配置选项", "settings", self._configure, "配置选中步骤自己的选项")
        add_btn("上移", "prev", lambda: self._move(-1))
        add_btn("下移", "next", lambda: self._move(1))
        add_btn("移除", "trash", self._remove_step)
        row.addStretch(1)
        self.root.addLayout(row)

        self.root.addWidget(Caption(
            "每个步骤都保存自己单独的选项，同一个功能可以添加多次；"
            "运行时使用步骤自带配置，不会改动程序本身的选项设置。"))

        self.add_footer("保存")
        self._refresh()

    # ------------------------------------------------------------ 列表
    def _refresh(self, keep_row: int | None = None) -> None:
        self.steps_list.clear()
        for i, step in enumerate(self._steps):
            spec = automation.STEP_TYPES[step["type"]]
            item = QListWidgetItem(f"{i + 1}. {spec.label} — {spec.summarize(step.get('config') or {})}")
            self.steps_list.addItem(item)
        if keep_row is not None and self.steps_list.count():
            self.steps_list.setCurrentRow(min(keep_row, self.steps_list.count() - 1))
        elif self.steps_list.count():
            self.steps_list.setCurrentRow(self.steps_list.count() - 1)

    def _current_index(self) -> int:
        return self.steps_list.currentRow()

    def _move(self, delta: int) -> None:
        index = self._current_index()
        target = index + delta
        if index < 0 or not 0 <= target < len(self._steps):
            return
        self._steps[index], self._steps[target] = self._steps[target], self._steps[index]
        self._refresh(keep_row=target)

    def _remove_step(self) -> None:
        index = self._current_index()
        if 0 <= index < len(self._steps):
            del self._steps[index]
            self._refresh(keep_row=min(index, len(self._steps) - 1))

    # ------------------------------------------------------------ 添加/配置
    def _add_step(self) -> None:
        menu = Menu(self)
        for key in automation.STEP_ORDER:
            action = menu.addAction(automation.STEP_TYPES[key].label)
            action.setData(key)
        sender = self.sender()
        pos = (sender.mapToGlobal(sender.rect().bottomLeft())
               if isinstance(sender, QWidget) and sender.isVisible() else self.cursor().pos())
        chosen = menu.exec(pos)
        if not chosen:
            return
        key = str(chosen.data())
        self._steps.append({"type": key, "config": deepcopy(automation.STEP_TYPES[key].default_config)})
        self._refresh(keep_row=len(self._steps) - 1)
        if automation.STEP_TYPES[key].has_options:
            self._configure()

    def _configure(self) -> None:
        index = self._current_index()
        if not 0 <= index < len(self._steps):
            self.notice("请先在列表里选中要配置的步骤。", kind="error")
            return
        step = self._steps[index]
        spec = automation.STEP_TYPES[step["type"]]
        if not spec.has_options:
            self.notice(f"「{spec.label}」没有可配置的选项。")
            return
        config = step.get("config") or {}
        if spec.key == "format":
            config = self._edit_format_config(config)
        elif spec.key == "replace":
            dialog = ReplaceStepDialog(dict(config), self)
            config = dict(dialog.config()) if dialog.exec() == BaseDialog.DialogCode.Accepted else None
        elif spec.key == "zhconv":
            dialog = ZhconvStepDialog(dict(config), self)
            config = dict(dialog.config()) if dialog.exec() == BaseDialog.DialogCode.Accepted else None
        if config is not None:
            step["config"] = config
        self._refresh(keep_row=index)

    def _edit_format_config(self, config: dict) -> dict | None:
        """用「格式整理选项」对话框编辑步骤自己的选项。

        传给对话框的是一份独立的 Settings 副本（步骤配置），不是程序
        当前的 self.settings —— 对话框里怎么改都碰不到程序配置。
        """
        tmp = Settings()
        for name in automation.FORMAT_FIELDS:
            if name in config:
                setattr(tmp, name, config[name])
        dialog = OptionsDialog(tmp, self)
        dialog.setWindowTitle("自动化步骤：格式整理选项")
        if dialog.exec() != BaseDialog.DialogCode.Accepted:
            return None
        return {name: getattr(tmp, name) for name in automation.FORMAT_FIELDS}

    # ------------------------------------------------------------ 保存
    def accept(self) -> None:                  # noqa: N802 - Qt 命名
        name = self.name_edit.text().strip()
        if not name:
            self.notice("请先给任务起个名字。", kind="error")
            return
        if name in self._taken and name != self._original_name:
            self.notice("已经有一个同名的自动化任务了。", kind="error")
            return
        if not self._steps:
            self.notice("请至少添加一个功能。", kind="error")
            return
        self.result_task = {"name": name, "steps": deepcopy(self._steps)}
        super().accept()


# ---------------------------------------------------------------- 步骤选项对话框
class ReplaceStepDialog(BaseDialog):
    """「查找替换」步骤的选项。"""

    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__("自动化步骤：查找替换", parent)
        self._config = dict(config)

        self.root.addWidget(SectionLabel("查找内容"))
        self.find_edit = MultiLineEdit("支持正则表达式", rows=2)
        self.find_edit.setText(str(config.get("pattern") or ""))
        self.root.addWidget(self.find_edit)

        self.root.addWidget(SectionLabel("替换为"))
        self.repl_edit = MultiLineEdit("留空表示删除匹配内容", rows=2)
        self.repl_edit.setText(str(config.get("replacement") or ""))
        self.root.addWidget(self.repl_edit)

        self.regex_check = QCheckBox("使用正则表达式")
        self.regex_check.setChecked(bool(config.get("use_regex", True)))
        self.case_check = QCheckBox("区分大小写")
        self.case_check.setChecked(bool(config.get("ignore_case", False)))
        self.root.addWidget(self.regex_check)
        self.root.addWidget(self.case_check)

        self.add_footer("保存")

    def config(self) -> dict:
        self._config.update({
            "pattern": self.find_edit.text(),
            "replacement": self.repl_edit.text(),
            "use_regex": self.regex_check.isChecked(),
            "ignore_case": self.case_check.isChecked(),
        })
        return self._config


class ZhconvStepDialog(BaseDialog):
    """「简繁转换」步骤的选项。"""

    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__("自动化步骤：简繁转换", parent)
        self._config = dict(config)
        self.root.addWidget(QLabel("选择转换方向："))
        self.combo = QComboBox()
        for label, mode in zhconv.CONVERT_MODES:
            self.combo.addItem(label, mode)
        index = self.combo.findData(config.get("mode", "t2s"))
        self.combo.setCurrentIndex(max(0, index))
        self.root.addWidget(self.combo)
        self.add_footer("保存")

    def config(self) -> dict:
        self._config["mode"] = str(self.combo.currentData())
        return self._config


__all__ = ["AutomationPanel", "AutomationDialog", "ReplaceStepDialog", "ZhconvStepDialog"]
