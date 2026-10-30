"""启动安装器并逐页截图（可靠版）。

关键点：
  * **抓图进程自己必须先声明 DPI 感知**：本机是 200% 缩放，不声明的话
    GetWindowRect 返回的是虚拟化（除以 2）的尺寸，PrintWindow 只画左上四分之一，
    看起来像"界面被裁切"，其实是抓图工具的问题。
  * 窗口物理尺寸要用 GetWindowRect 读，不要猜；200% 缩放下是 1306x871 而不是 653x436。
  * PrintWindow 有时在窗口刚显示时抓到半张图 —— 抓之前先 SetForegroundWindow + 等一会。
  * 用 BM_CLICK 点按钮（不移动鼠标），点完等 UI 重绘再抓下一页。

    C:\\Users\\Rex\\.workbuddy\\binaries\\python\\versions\\3.13.12\\python.exe tools/shot_installer.py [--uninstall]
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

# 必须在任何窗口枚举之前声明 DPI 感知（等价于 app.manifest 里的 dpiAware）
try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SETUP = os.path.join(ROOT, "installer", "winforms", "bin", "Release", "net48", "txtFormat-Setup.exe")
OUT = os.path.join(os.environ["TEMP"], "tfsetup-shots")

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
PWFULL = 0x00000002
BM_CLICK = 0x00F5


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


def grab(hwnd: int, path: str) -> tuple[int, int]:
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return (0, 0)

    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, PWFULL)

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)

    from PIL import Image
    Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB").save(path)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    return (w, h)


def find_window(title_part: str, timeout: float = 25.0) -> int:
    end = time.time() + timeout
    while time.time() < end:
        found: list[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n == 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if title_part in buf.value:
                found.append(hwnd)
            return True

        user32.EnumWindows(cb, 0)
        if found:
            return found[0]
        time.sleep(0.25)
    return 0


def click(hwnd: int, *labels: str) -> str | None:
    """按标签找按钮并 BM_CLICK；返回实际点到的标签。"""
    for label in labels:
        target: list[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def cb(child, _):
            n = user32.GetWindowTextLengthW(child)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(child, buf, n + 1)
                if buf.value == label:
                    target.append(child)
            return True

        user32.EnumChildWindows(hwnd, cb, 0)
        if target:
            user32.SendMessageW(target[0], BM_CLICK, 0, 0)
            return label
    return None


def snapshot(hwnd: int, name: str) -> None:
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.7)
    w, h = grab(hwnd, os.path.join(OUT, name))
    print(f"  截图 → {name}  ({w}x{h})  [{window_title_of_page(hwnd)}]")


def child_texts(hwnd: int) -> list[str]:
    out: list[str] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(child, _):
        n = user32.GetWindowTextLengthW(child)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(child, buf, n + 1)
            out.append(buf.value)
        return True

    user32.EnumChildWindows(hwnd, cb, 0)
    return out


def window_title_of_page(hwnd: int) -> str:
    """右侧内容区的大标题（14pt 粗体那个 Label）—— 用来确认截图和页码对得上。"""
    for t in child_texts(hwnd):
        if len(t) < 40 and ("安装" in t or "欢迎" in t or "选择" in t
                           or "许可" in t or "准备" in t) and len(t) > 3:
            # 标题是短句且不含句号结尾的说明文字
            if not t.endswith("。") and "：" not in t:
                return t
    return "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uninstall", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith(".png"):
            os.remove(os.path.join(OUT, f))

    title = "卸载 txtFormat" if args.uninstall else "txtFormat 安装"
    if args.uninstall:
        # 直接以 --uninstall-run <目录> 启动：跳过"复制到临时目录再拉起"那一步，
        # 这样截图进程能直接持有卸载向导窗口（真卸载仍走 uninstall.exe）。
        installed = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Programs", "txtFormat")
        if not os.path.isdir(installed):
            print(f"[错误] 未安装：{installed}（先跑一次安装向导）")
            return 1
        cmd = [SETUP, "--uninstall-run", installed]
    else:
        cmd = [SETUP]

    proc = subprocess.Popen(cmd, cwd=os.path.dirname(SETUP))
    hwnd = find_window(title)
    if not hwnd:
        print(f"[错误] 没等到窗口（{title}）")
        proc.terminate()
        return 1

    steps = ["卸载"] if args.uninstall else ["下一步"] * 5 + ["安装"]
    snapshot(hwnd, "00.png")
    for i, label in enumerate(steps, start=1):
        hit = click(hwnd, label, "完成", "关闭", "取消")
        if hit is None:
            print(f"[提示] 第 {i} 步没找到按钮，停在当前页")
            break
        time.sleep(1.3)
        snapshot(hwnd, f"{i:02d}.png")
        if hit in ("完成", "关闭"):
            break

    time.sleep(0.5)
    try:
        proc.terminate()
    except Exception:
        pass
    print(f"\n截图目录：{OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())