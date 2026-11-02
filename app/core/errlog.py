"""崩溃日志（规范 §十一：exe 同目录放 ``error.log``）。

规范 §七 4 规定：未捕获异常 → 写 ``error.log`` + 状态栏红字 + 自绘错误框，
**不弹系统框、不静默退出**。

这里只管写盘。写盘必须**不能自己再抛** —— 日志写失败时如果再抛异常，
就会把真正的崩溃原因盖掉。所以全程 try/except 吞掉，失败也不影响退出流程。
"""

from __future__ import annotations

import os
import traceback
from datetime import datetime

from .paths import root_dir

#: 日志文件名（规范 §十一：exe 同目录）
LOG_NAME = "error.log"

#: 最多保留多少字节 —— 免得日志无限长
MAX_BYTES = 512 * 1024


def log_path() -> str:
    """error.log 的完整路径（exe 同目录）。"""
    return os.path.join(root_dir(), LOG_NAME)


def write_exception(exc: BaseException, context: str = "") -> str:
    """把异常写进 error.log，返回日志路径。写失败返回空串。

    只截最近一段（超过 MAX_BYTES 就砍掉前半截），免得日志无限长。
    """
    path = log_path()
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        head = f"\n===== {stamp} =====\n"
        if context:
            head += f"上下文：{context}\n"
        body = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        text = head + body

        # 已存在就先读出来，超长就砍掉前半段再写
        try:
            if os.path.exists(path) and os.path.getsize(path) > MAX_BYTES:
                with open(path, "rb") as fh:
                    fh.seek(-MAX_BYTES // 2, os.SEEK_END)
                    old = fh.read().decode("utf-8", errors="replace")
                text = "\n（前半段已省略）\n" + old + text
        except OSError:
            pass

        with open(path, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(text)
        return path
    except Exception:      # noqa: BLE001 - 写日志失败绝不能再抛
        return ""


#: 状态栏红字通道：主窗口启动时注册（规范 §七.4 的第二个通道）。
#: 用回调而不是 import 主窗口 —— core 层不依赖 ui 层。
_error_sink = None


def set_error_sink(sink) -> None:
    """注册「状态栏红字」回调：``sink(text)``，主窗口传自己的方法进来。"""
    global _error_sink
    _error_sink = sink


def _notify_status(text: str) -> None:
    sink = _error_sink
    if sink is None:
        return
    try:
        sink(text)
    except Exception:      # noqa: BLE001 - 状态栏没画出来也不能盖掉原异常
        pass


def install_excepthook() -> None:
    """挂上全局异常钩子：未捕获异常写 error.log + 状态栏红字 + 自绘错误框（规范 §七.4）。

    打包成 exe 后 stderr 是看不见的 —— 只写日志不弹框，用户看到的就是
    「无声消失」（规范 §七.4 明令禁止的静默失败）。所以钩子里要：

    1. 写 ``error.log``（失败也不影响后续）；
    2. 主窗口还活着时把状态栏文字变红（第二个通道）；
    3. QApplication 还活着时弹一个**自绘**错误框（带「打开日志」入口），
       不用系统 MessageBox、不发声；
    4. 兜底把异常交还旧钩子（offscreen/测试环境下弹不了框也能留痕）。
    """
    old_hook = __import__("sys").excepthook

    def hook(exc_type, exc_value, exc_tb):    # noqa: ANN001 - sys.excepthook 签名
        path = ""
        try:
            path = write_exception(exc_value)
        except Exception:      # noqa: BLE001
            pass
        _notify_status("出错，详见 error.log")
        try:
            _show_error_dialog(exc_value, path)
        except Exception:      # noqa: BLE001 - 弹框失败绝不能再炸
            pass
        old_hook(exc_type, exc_value, exc_tb)

    __import__("sys").excepthook = hook


def _show_error_dialog(exc: BaseException | None, log_path: str) -> None:
    """自绘错误框（规范 §七.4 的第三个通道）。

    具体外观在 ``app/ui/errdialog.py``（DWM 定制 / 定宽不可拉伸 / 标题只写程序名），
    这里只管把异常翻成一句人话。
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    from ..ui.errdialog import show_error

    message = "发生了未知错误。" if exc is None else str(exc) or exc.__class__.__name__
    # 带上 parent：否则 QDialog 会弹到屏幕正中（主窗在副屏时就跑到另一块屏上去了）。
    # 防叠弹由 show_error 内部的 _showing 标志负责。
    show_error(message, log_path, app.activeWindow())


__all__ = ["LOG_NAME", "log_path", "write_exception", "install_excepthook",
           "set_error_sink"]
