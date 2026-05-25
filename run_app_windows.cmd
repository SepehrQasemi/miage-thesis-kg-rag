@echo off
setlocal

if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
)

python scripts\run_web_app.py --host 127.0.0.1 --port 8000
endlocal
