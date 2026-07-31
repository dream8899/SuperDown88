@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
if "%SUPERMEDIA_ROOT%"=="" (
  set "ROOT=%CD%\Video_Download"
) else (
  set "ROOT=%SUPERMEDIA_ROOT%"
)
python "%SCRIPT_DIR%supermedia_console.py" --root "%ROOT%" update
pause
