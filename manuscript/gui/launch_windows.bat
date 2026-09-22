@echo off
setlocal EnableExtensions

rem Convenience launcher.  Prefer the packaged standalone app when available.
set "HERE=%~dp0"
set "EXE=%HERE%dist\SRAM-Vmin-Inverse-Studio\SRAM-Vmin-Inverse-Studio.exe"

if exist "%EXE%" (
  "%EXE%"
  exit /b %ERRORLEVEL%
)

if exist "%HERE%.venv\Scripts\python.exe" (
  "%HERE%.venv\Scripts\python.exe" "%HERE%demo_server.py"
  exit /b %ERRORLEVEL%
)

echo [ERROR] No packaged executable or local Python environment was found.
echo Read README_KR.md, then build the standalone folder with build_windows.bat.
exit /b 1
