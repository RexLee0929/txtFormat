@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo   txtFormat 长文本整理工具 1.0.2  构建
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
