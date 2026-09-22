@echo off
setlocal EnableExtensions

rem Build a self-contained Windows *folder* for the local-only presentation UI.
rem Run this file from Windows after following README_KR.md.  Build on Windows;
rem PyInstaller does not create a Windows executable from Linux/macOS.

set "HERE=%~dp0"
cd /d "%HERE%"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Missing .venv\Scripts\python.exe
  echo Create it and install requirements-windows.txt first.  See README_KR.md.
  exit /b 1
)

if not exist "demo_bundle\read_inference_bundle.pt" (
  echo [ERROR] Missing demo_bundle\read_inference_bundle.pt
  echo Create the trusted local bundle with prepare_bundle.py on an authorized machine.
  exit /b 1
)
if not exist "demo_bundle\write_inference_bundle.pt" (
  echo [ERROR] Missing demo_bundle\write_inference_bundle.pt
  echo Create the trusted local bundle with prepare_bundle.py on an authorized machine.
  exit /b 1
)

echo [1/2] Running source-level smoke tests...
".venv\Scripts\python.exe" -m unittest tests.test_demo_engine -v
if errorlevel 1 exit /b 1

echo [2/2] Packaging local-only Windows application...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --onedir --console ^
  --name "SRAM-Vmin-Inverse-Studio" ^
  --paths "..\..\python" ^
  --collect-submodules src ^
  --collect-all torch ^
  --collect-all gpytorch ^
  --collect-all pandas ^
  --collect-all openpyxl ^
  --add-data "static;static" ^
  --add-data "demo_bundle;demo_bundle" ^
  --distpath "dist" ^
  --workpath "build" ^
  --specpath "build" ^
  demo_server.py
if errorlevel 1 exit /b 1

echo.
echo Build complete:
echo   %HERE%dist\SRAM-Vmin-Inverse-Studio\SRAM-Vmin-Inverse-Studio.exe
echo Copy the entire SRAM-Vmin-Inverse-Studio folder to the presentation PC.
echo This folder contains confidential local model assets; do not upload it.
exit /b 0
