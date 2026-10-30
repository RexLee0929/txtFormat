@echo off
rem 首次使用：创建虚拟环境并安装依赖
setlocal
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv || (echo 创建虚拟环境失败，请确认已安装 Python 3.11+ & exit /b 1)
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
echo 安装完成。运行 run.cmd 启动。
endlocal
