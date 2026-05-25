@echo off
setlocal

if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
)

python scripts\setup_ollama.py --install --pull --model qwen2.5:7b
python scripts\doctor.py

endlocal
