"""后台任务：把耗时计算从 UI 线程挪走。

为什么需要：格式整理 / 广告扫描 / 一键审核都是「全文正则」级的活，5MB 小说
要跑几秒。以前它们全在 UI 线程里同步执行，Windows 会直接把窗口标成"未响应"，
用户以为程序卡死了。

这里只做一件事：把一个可调用对象丢到 QThread 里跑，结果用信号送回 UI 线程
（Qt 的跨线程信号会自动排队，所以回调里可以直接碰控件）。
"""

from __future__ import annotations

import traceback
from collections.abc import Callable

from PySide6.QtCore import QThread, Signal


class Task(QThread):
    """在后台线程执行 ``fn(*args, **kwargs)``，结果通过信号回传。"""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object], parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:                    # noqa: D401 - QThread 要求
        try:
            result = self._fn()
        except Exception as exc:              # noqa: BLE001 - 交给 UI 侧展示
            traceback.print_exc()
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.done.emit(result)


def start_task(owner, fn: Callable[[], object], on_done: Callable[[object], None],
               on_error: Callable[[str], None] | None = None) -> bool:
    """在 ``owner`` 上挂一个后台任务（同一 owner 同时只允许一个）。

    ``owner`` 需要能存属性（QWidget/QDialog 都行）；任务对象挂在 owner 上，
    避免 Python 侧被回收导致的悬空线程。返回 False 表示上一个还没跑完。
    """
    running = getattr(owner, "_bg_task", None)
    if running is not None and running.isRunning():
        return False
    task = Task(fn, parent=owner)
    owner._bg_task = task
    task.done.connect(on_done)
    if on_error is not None:
        task.failed.connect(on_error)
    task.start()
    return True


def task_running(owner) -> bool:
    running = getattr(owner, "_bg_task", None)
    return running is not None and running.isRunning()


def wait_task(owner, msec: int = 3000) -> None:
    """关窗/关对话框前等后台任务收尾（QThread 在运行中被析构会直接崩）。"""
    running = getattr(owner, "_bg_task", None)
    if running is not None and running.isRunning():
        running.wait(msec)


__all__ = ["Task", "start_task", "task_running", "wait_task"]
