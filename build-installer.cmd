@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo   txtFormat 长文本整理工具 1.0.2  生成安装包
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
        "artifacts\txtFormat-1.0.2-setup.exe" >nul
if errorlevel 1 goto :fail

echo.
echo 安装包已生成：artifacts\txtFormat-1.0.2-setup.exe
echo 安装后可从「设置 - 应用」或安装目录下的 uninstall.exe 卸载。
echo.
pause
exit /b 0

:fail
echo.
echo 生成失败，请查看上方的错误信息。
pause
exit /b 1
