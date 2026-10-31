#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GBK 编码写 .cmd/.bat 文件。

Write 工具落的是 UTF-8，在 GBK 控制台里中文会变成乱码；
批处理脚本一律走本脚本生成，保证 cmd 读得对。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.version import APP_VERSION                      # noqa: E402


def w(path: Path, text: str) -> None:
    path.write_bytes(text.replace("\n", "\r\n").encode("gbk"))
    print(f"  写入 {path.name}  ({path.stat().st_size} B, GBK)")


BUILD = r"""@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo   txtFormat 长文本整理工具 __VER__  构建
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境，请先运行 setup.cmd
    goto :fail
)

echo [1/3] 安装构建依赖 ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q pyinstaller
if errorlevel 1 goto :fail

echo [2/3] 生成程序图标 ...
".venv\Scripts\python.exe" tools\make_icon.py
if errorlevel 1 goto :fail

echo [3/3] 打包主程序 ...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath artifacts txtFormat.spec
if errorlevel 1 goto :fail

echo.
echo 构建完成：artifacts\txtFormat\txtFormat.exe
echo 生成安装包请运行 build-installer.cmd
echo.
pause
exit /b 0

:fail
echo.
echo 构建失败，请查看上方的错误信息。
pause
exit /b 1
"""

BUILD_INSTALLER = r"""@echo off
setlocal
cd /d "%~dp0"

rem 版本号唯一来源是 installer\version.props（规范：改版本只改那一处）。
rem 脚本在运行时读它，不手抄版本号 —— 手抄必漏（实测 1.0.2 出现过 3 处）。
set "VER="
for /f "tokens=3 delims=<>" %%a in ('findstr /r /c:"^[ ]*<Version>[0-9]" installer\version.props') do set "VER=%%a"
if "%VER%"=="" (
    echo [错误] 无法从 installer\version.props 读取版本号。
    goto :fail
)

echo.
echo ==========================================
echo   txtFormat 长文本整理工具 %VER%  生成安装包
echo ==========================================
echo.

if not exist "artifacts\txtFormat\txtFormat.exe" (
    echo [错误] 还没有主程序产物，请先运行 build.cmd
    goto :fail
)

where dotnet >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 .NET SDK（需要 6.0 或更高版本）
    echo        https://dotnet.microsoft.com/download
    goto :fail
)

echo [1/3] 生成内嵌数据 payload.zip ...
".venv\Scripts\python.exe" tools\make_payload.py
if errorlevel 1 goto :fail

echo [2/3] 编译自绘安装向导 ...
pushd installer\winforms
dotnet build -c Release -v minimal
if errorlevel 1 ( popd & goto :fail )
popd

echo [3/3] 收拢产物 ...
if not exist "artifacts" mkdir "artifacts"
copy /y "installer\winforms\bin\Release\net48\txtFormat-Setup.exe" ^
        "artifacts\txtFormat-%VER%-setup.exe" >nul
if errorlevel 1 goto :fail

echo.
echo 安装包已生成：artifacts\txtFormat-%VER%-setup.exe
echo 安装后可从「设置 - 应用」或安装目录下的 uninstall.exe 卸载。
echo.
pause
exit /b 0

:fail
echo.
echo 生成失败，请查看上方的错误信息。
pause
exit /b 1
"""

if __name__ == "__main__":
    w(ROOT / "build.cmd", BUILD.replace("__VER__", APP_VERSION))
    # 安装器脚本的版本号在运行时从 version.props 读（见脚本头部），不做字面替换
    w(ROOT / "build-installer.cmd", BUILD_INSTALLER)
    print(f"完成（版本 {APP_VERSION}）。")