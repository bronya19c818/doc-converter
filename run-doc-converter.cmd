@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 未找到本地运行环境。请先执行 uv sync --group dev。
  exit /b 1
)

".venv\Scripts\python.exe" -m doc_converter.launcher
