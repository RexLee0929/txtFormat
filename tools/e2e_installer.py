"""安装包端到端验证：静默安装 → 校验文件/注册表/快捷方式 → 自检 → 静默卸载 → 查残留。

    python tools/e2e_installer.py <setup.exe 路径>
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
import winreg

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def expect_version() -> str:
    """版本唯一来源：app/core/version.py 的 APP_VERSION。

    不在脚本里写死版本号 —— 写死必漏（1.0.2 时代这里漏过两处断言）。
    直接按文件路径加载 version.py，不经过 app 包的 __init__，避免拖进 UI 依赖。
    """
    p = os.path.join(ROOT, "app", "core", "version.py")
    spec = importlib.util.spec_from_file_location("tf_version", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.APP_VERSION


PASS = 0
FAIL = 0
NOTES: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {name}")
    else:
        FAIL += 1
        NOTES.append(f"{name} {extra}")
        print(f"  [FAIL] {name}  {extra}")


def localappdata() -> str:
    return os.environ.get("LOCALAPPDATA", "")


def main() -> int:
    setup = os.path.abspath(sys.argv[1])
    ver_expect = expect_version()
    print(f"安装包：{setup}  ({os.path.getsize(setup) // 1024 // 1024} MB)")
    print(f"期望版本（读自 app/core/version.py）：{ver_expect}")

    # 默认是「仅为我安装」→ %LOCALAPPDATA%\Programs\txtFormat
    target = os.path.join(localappdata(), "Programs", "txtFormat")

    # 从干净状态开始：上一轮卸载默认「保留配置」，会留下 config.json / custreg.txt，
    # 不清掉的话「安装器未预置 config.json」必然误报（实测踩过）。
    if os.path.isdir(target):
        import shutil
        print(f"清理上一轮残留：{target}")
        shutil.rmtree(target, ignore_errors=True)

    listenv = dict(os.environ, TMP=os.environ.get("TEMP", r"C:\Windows\Temp"))
    proc = subprocess.Popen([setup, "--silent"], env=listenv,
                            stdin=subprocess.DEVNULL)
    rc = proc.wait(timeout=300)
    print(f"\n静默安装退出码 = {rc}")
    check("静默安装成功", rc == 0, f"rc={rc}")

    print(f"安装目录：{target}")
    check("安装目录存在", os.path.isdir(target))

    exe = os.path.join(target, "txtFormat.exe")
    check("主程序存在", os.path.isfile(exe))
    check("README.md 已装入", os.path.isfile(os.path.join(target, "README.md")))
    check("custreg.txt 已装入", os.path.isfile(os.path.join(target, "custreg.txt")))
    check("安装器未预置 config.json",
          not os.path.isfile(os.path.join(target, "config.json")),
          "payload 不该带设置文件（规范 §三.2：由程序首次运行时创建）")
    check("uninstall.exe 已生成", os.path.isfile(os.path.join(target, "uninstall.exe")))

    # 文件数
    n = sum(len(f) for _, _, f in os.walk(target))
    print(f"安装文件总数 = {n}")
    check("文件数 > 80", n > 80, str(n))

    # 注册表：卸载键
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Uninstall\txtFormat") as k:
            disp = winreg.QueryValueEx(k, "DisplayName")[0]
            ver = winreg.QueryValueEx(k, "DisplayVersion")[0]
            pub = winreg.QueryValueEx(k, "Publisher")[0]
            contact = winreg.QueryValueEx(k, "Contact")[0]
        print(f"注册表：{disp} / {ver} / {pub} / {contact}")
        check(f"注册表 DisplayVersion = {ver_expect}", ver == ver_expect, ver)
        check("注册表 Publisher = Rex Lee", pub == "Rex Lee", pub)
        check("注册表 Contact = 邮箱", contact == "rexlee@rexleepro.com", contact)
    except OSError as exc:
        check("卸载注册键存在", False, str(exc))

    # App Paths
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\App Paths\txtFormat.exe") as k:
            ap = winreg.QueryValueEx(k, "")[0]
        check("App Paths 指向主程序", os.path.normcase(ap) == os.path.normcase(exe), ap)
    except OSError as exc:
        check("App Paths 存在", False, str(exc))

    # 快捷方式（桌面可能被 OneDrive 重定向）
    desktop = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[Environment]::GetFolderPath('Desktop')"],
        capture_output=True, text=True, timeout=60).stdout.strip()
    lnk = os.path.join(desktop, "txtFormat.lnk")
    print(f"桌面快捷方式：{lnk}")
    check("桌面快捷方式存在", os.path.isfile(lnk))

    f_lnk = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                         "Start Menu", "Programs", "txtFormat.lnk")
    check("开始菜单快捷方式存在", os.path.isfile(f_lnk))

    # 从安装目录跑自检（窗口程序，结果写 json 文件，不靠 stdout）
    print("\n--- 安装目录自检 ---")
    out_dir = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "tf-selftest")
    if os.path.isdir(out_dir):
        import shutil
        shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    subprocess.run([exe, "--selftest", out_dir], capture_output=True,
                        text=True, timeout=300, encoding="utf-8", errors="replace")
    report_path = os.path.join(out_dir, "selftest.json")
    check("自检报告已生成", os.path.isfile(report_path), report_path)
    report = {}
    if os.path.isfile(report_path):
        import json
        with open(report_path, encoding="utf-8") as fh:
            report = json.load(fh)
        for c in report.get("checks", []):
            mark = "OK  " if c["ok"] else "FAIL"
            print(f"  [{mark}] {c['name']}  {c['detail'][:90]}")
    check("自检全部通过", bool(report.get("ok")), str(report.get("checks"))[:300])
    check(f"自检版本 = {ver_expect}", report.get("version") == ver_expect, str(report.get("version")))

    # 规范 §三.2：程序首次运行就要落盘一份默认 config.json（让安装器的配置检测成立）。
    # 自检跑过 = 窗口建过 = MainWindow.__init__ 执行过 ensure_default()。
    cfg = os.path.join(target, "config.json")
    check("程序首次运行已落盘 config.json", os.path.isfile(cfg),
          "MainWindow 启动时应 ensure_default（规范 §三.2）")

    # 静默卸载
    print("\n--- 静默卸载 ---")
    un = os.path.join(target, "uninstall.exe")
    up = subprocess.Popen([un, "--silent"], stdin=subprocess.DEVNULL)
    urc = up.wait(timeout=300)
    print(f"卸载退出码 = {urc}")
    time.sleep(3)

    # 静默卸载默认「保留个人设置」→ 安装目录里只剩 config.json / custreg.txt 这类用户文件
    allowed = {"config.json", "custreg.txt", "custerr.txt", "error.log"}
    if os.path.isdir(target):
        extra = sorted(f for f in os.listdir(target) if f not in allowed)
        check("安装目录仅剩个人设置", not extra, str(extra))
        check("自定义正则按预期保留",
              os.path.isfile(os.path.join(target, "custreg.txt")))
    else:
        check("安装目录仅剩个人设置", True, "目录已清空删除")
        check("自定义正则按预期保留", False, "安装目录不存在")
    check("桌面快捷方式已删除", not os.path.isfile(lnk))
    check("开始菜单快捷方式已删除", not os.path.isfile(f_lnk))

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Uninstall\txtFormat"):
            check("卸载注册键已删除", False)
    except OSError:
        check("卸载注册键已删除", True)

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\App Paths\txtFormat.exe"):
            check("App Paths 已删除", False)
    except OSError:
        check("App Paths 已删除", True)

    prefs = os.path.join(os.environ.get("APPDATA", ""), "txtFormat")
    check("旧版 %APPDATA% 目录按预期保留", os.path.isdir(prefs), prefs)

    print(f"\n通过 {PASS} 项，失败 {FAIL} 项")
    for n in NOTES:
        print(f"  ! {n}")
    print("端到端验证通过 ✓" if FAIL == 0 else "端到端验证失败 ✗")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())