@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"

if not exist ".venv\Scripts\python.exe" (
  echo 未找到本地运行环境。请先执行 uv sync --frozen --group dev。
  if "%~1"=="" pause
  exit /b 1
)

".venv\Scripts\python.exe" -m doc_converter.launcher %*
set "launch_exit=%errorlevel%"
if not "%launch_exit%"=="0" (
  echo 启动失败，请查看上方错误信息。
  if "%~1"=="" pause
)
exit /b %launch_exit%
