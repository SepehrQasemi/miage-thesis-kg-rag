@echo off
setlocal

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or newer, then run this file again.
  exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
  echo Docker was not found. Install Docker Desktop, start it, then run this file again.
  exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
  echo Docker Desktop is installed but the Docker engine is not running.
  echo Start Docker Desktop, wait until it is ready, then run this file again.
  exit /b 1
)

echo Starting local Neo4j database...
docker compose up -d neo4j
if errorlevel 1 (
  echo Neo4j could not be started with Docker Compose.
  exit /b 1
)

if not exist .venv (
  python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python scripts\setup_project.py --install-deps
if errorlevel 1 exit /b 1

choice /C YN /M "Optional: install Ollama and pull qwen2.5:7b for local LLM suggestions"
if errorlevel 2 goto skip_ollama
python scripts\setup_ollama.py --install --pull --model qwen2.5:7b

:skip_ollama
python scripts\doctor.py

echo.
echo Start the app with:
echo   run_app_windows.cmd
endlocal
