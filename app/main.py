"""程序入口。

只管启动：单实例互斥、窗口创建、命令行文件打开。
打包自检（``--selftest`` / ``--menutest``）在 :mod:`app.selftest`，按参数懒加载。
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .core.errlog import install_excepthook
from .core.paths import asset
from .core.version import APP_NAME, APP_VERSION
from .ui.main_window import MainWindow
from .ui.theme import apply_dwm_chrome

#: 单实例互斥用的本地套接字名（规范 §七.6：双开不开两个窗口，激活已有窗口）
_INSTANCE_KEY = APP_NAME + "-instance"


def _already_running() -> bool:
    """已有实例在跑就激活它的窗口并返回 True。

    用 QLocalServer 做互斥：连得上 = 已有实例（发个「show」让它弹到前台）；
    连不上 = 本进程是第一个，随后开始监听。崩溃残留的管道名先清掉。
    """
    probe = QLocalSocket()
    probe.connectToServer(_INSTANCE_KEY)
    if probe.waitForConnected(200):
        probe.write(b"show\n")
        probe.flush()
        probe.waitForBytesWritten(200)
        probe.disconnectFromServer()
        return True
    return False


def _start_instance_server(window) -> QLocalServer | None:
    """监听单实例管道；后续实例连进来就把主窗口拉到前台。"""
    QLocalServer.removeServer(_INSTANCE_KEY)     # 清掉上次崩溃的残留
    server = QLocalServer()
    if not server.listen(_INSTANCE_KEY):
        return None

    def _on_connection() -> None:
        sock = server.nextPendingConnection()
        if sock is None:
            return
        sock.readyRead.connect(lambda: _activate(window, sock))

    server.newConnection.connect(_on_connection)
    return server


def _activate(window, sock) -> None:
    """已有实例被二次启动：窗口弹到前台 + 状态栏瞬时提示（不弹「已在运行」框）。"""
    try:
        sock.readAll()
    except Exception:       # noqa: BLE001
        pass
    window.setWindowState((window.windowState() & ~Qt.WindowState.WindowMinimized)
                          | Qt.WindowState.WindowActive)
    window.showNormal()
    window.raise_()
    window.activateWindow()
    window.toast.show_message(f"{APP_NAME} 已在运行")


def _flag_dir(flag: str) -> str:
    """取 ``--selftest <目录>`` 这类参数里的目录（缺省当前目录）。"""
    index = sys.argv.index(flag)
    raw = sys.argv[index + 1] if len(sys.argv) > index + 1 else os.getcwd()
    return os.path.abspath(raw)


def main() -> int:
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)

    # 规范 §十一：未捕获异常要写 exe 同目录的 error.log（崩了有据可查）
    install_excepthook()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    # 不设置 applicationDisplayName：Qt 会把「程序显示名」追加到窗口标题后面，
    # 导致标题栏出现「文件名 — txtFormat 1.0.1 - txtFormat」这种重复尾巴。
    app.setApplicationDisplayName("")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("txtFormat")
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))

    icon_path = asset("app.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 隐藏自检入口：txtFormat.exe --selftest <输出目录>（模块懒加载，正常启动不碰）
    if "--selftest" in sys.argv:
        from .selftest import selftest
        return selftest(app, _flag_dir("--selftest"))

    # 隐藏菜单黑角自检：txtFormat.exe --menutest <输出目录>
    if "--menutest" in sys.argv:
        from .selftest import menutest
        return menutest(app, _flag_dir("--menutest"))

    # 单实例互斥（规范 §七.6：程序已在运行 → 激活已有窗口，不开第二个）
    if _already_running():
        return 0

    window = MainWindow()
    window.show()
    # 窗口已建出真实句柄后再定制标题栏（过早调用拿不到有效的 hwnd）
    apply_dwm_chrome(int(window.winId()))
    _start_instance_server(window)

    # 命令行传入的文件直接打开
    for arg in sys.argv[1:]:
        if os.path.isfile(arg):
            window.open_path(os.path.abspath(arg))
            break

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
