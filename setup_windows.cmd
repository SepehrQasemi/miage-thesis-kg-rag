@echo off
setlocal

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or newer, then run this file again.
  exit /b 1
)

if not exist .venv (
  python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python scripts\setup_project.py --install-deps --install-playwright

choice /M "Install optional Ollama and pull qwen2.5:7b for LLM suggestions"
if errorlevel 2 goto skip_ollama
python scripts\setup_ollama.py --install --pull --model qwen2.5:7b

:skip_ollama
python scripts\doctor.py

echo.
echo Start the app with:
echo   run_app_windows.cmd
endlocal
