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


def install_excepthook() -> None:
    """挂上全局异常钩子：未捕获异常写 error.log + 自绘错误框（规范 §七.4）。

    打包成 exe 后 stderr 是看不见的 —— 只写日志不弹框，用户看到的就是
    「无声消失」（规范 §七.4 明令禁止的静默失败）。所以钩子里要：

    1. 写 ``error.log``（失败也不影响后续）；
    2. QApplication 还活着时弹一个**自绘**错误框（带「打开日志」入口），
       不用系统 MessageBox、不发声；
    3. 兜底把异常交还旧钩子（offscreen/测试环境下弹不了框也能留痕）。
    """
    old_hook = __import__("sys").excepthook

    def hook(exc_type, exc_value, exc_tb):    # noqa: ANN001 - sys.excepthook 签名
        path = ""
        try:
            path = write_exception(exc_value)
        except Exception:      # noqa: BLE001
            pass
        try:
            _show_error_dialog(exc_value, path)
        except Exception:      # noqa: BLE001 - 弹框失败绝不能再炸
            pass
        old_hook(exc_type, exc_value, exc_tb)

    __import__("sys").excepthook = hook


def _show_error_dialog(exc: BaseException | None, log_path: str) -> None:
    """自绘错误框：发生了什么 + 下一步怎么做 + 「打开日志」入口。

    只在 QApplication 已存在（事件循环还活着）时弹；对话框样式与主窗口
    同一套（自绘、白底、无系统图标、不发声）。
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
                                   QPushButton, QVBoxLayout)

    app = QApplication.instance()
    if app is None:
        return

    from .version import APP_NAME

    message = "发生了未知错误。" if exc is None else str(exc) or exc.__class__.__name__
    if len(message) > 200:
        message = message[:200] + "…"

    dlg = QDialog()
    dlg.setWindowTitle(APP_NAME + " 遇到问题")
    dlg.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
    dlg.setMinimumWidth(420)
    try:
        from .ui.theme import stylesheet
        dlg.setStyleSheet(stylesheet())
    except Exception:      # noqa: BLE001
        pass

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(20, 18, 20, 16)
    lay.setSpacing(12)
    head = QLabel(APP_NAME + " 遇到问题，需要关闭。")
    head.setStyleSheet("font-weight: 600; font-size: 13px;")
    lay.addWidget(head)
    body = QLabel(message + "\n\n已把错误详情写入 error.log，可以打开日志查看。")
    body.setWordWrap(True)
    body.setStyleSheet("font-size: 12px;")
    lay.addWidget(body, 1)

    row = QHBoxLayout()
    row.addStretch(1)
    if log_path and os.path.exists(log_path):
        log_btn = QPushButton("打开日志")

        def _open_log() -> None:
            try:
                os.startfile(log_path)                      # noqa: S606
            except Exception:   # noqa: BLE001
                pass
            dlg.accept()

        log_btn.clicked.connect(_open_log)
        row.addWidget(log_btn)
    close = QPushButton("关闭")
    close.setDefault(True)
    close.clicked.connect(dlg.accept)
    row.addWidget(close)
    lay.addLayout(row)

    dlg.exec()


__all__ = ["LOG_NAME", "log_path", "write_exception", "install_excepthook"]
