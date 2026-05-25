import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


DEFAULT_MODEL = "qwen2.5:7b"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"


def run(command: list[str], timeout: int | None = None) -> None:
    print(">", " ".join(command))
    completed = subprocess.run(command, timeout=timeout)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def ollama_exe() -> str | None:
    return shutil.which("ollama")


def winget_exe() -> str | None:
    return shutil.which("winget")


def brew_exe() -> str | None:
    return shutil.which("brew")


def install_ollama() -> None:
    if ollama_exe():
        print("Ollama is already installed.")
        return

    system = platform.system().lower()
    if system == "windows":
        winget = winget_exe()
        if not winget:
            raise SystemExit(
                "Ollama is not installed and winget was not found. "
                "Install Ollama manually from https://ollama.com/download/windows"
            )
        run(
            [
                winget,
                "install",
                "--id",
                "Ollama.Ollama",
                "-e",
                "--accept-source-agreements",
                "--accept-package-agreements",
            ]
        )
    elif system == "darwin":
        brew = brew_exe()
        if not brew:
            raise SystemExit(
                "Ollama is not installed and Homebrew was not found. "
                "Install Ollama manually from https://ollama.com/download/mac"
            )
        run([brew, "install", "ollama"])
    else:
        raise SystemExit(
            "Automatic Ollama installation is only implemented for Windows winget and macOS Homebrew. "
            "On Linux, install Ollama from https://ollama.com/download/linux, then rerun this script with --pull."
        )

    if not ollama_exe():
        raise SystemExit("Ollama installation finished, but the ollama command is not on PATH. Restart the terminal and retry.")


def start_ollama_if_needed(timeout: int) -> None:
    if ollama_api_ready(timeout=3):
        return
    exe = ollama_exe()
    if not exe:
        raise SystemExit("Ollama command not found.")
    print("Starting Ollama service in the background...")
    subprocess.Popen(
        [exe, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system().lower() == "windows" else 0,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ollama_api_ready(timeout=2):
            return
        time.sleep(1)
    raise SystemExit("Ollama did not become ready in time.")


def ollama_api_ready(timeout: int) -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def installed_models(timeout: int) -> set[str]:
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return set()
    names = set()
    for item in data.get("models", []):
        for key in ("name", "model"):
            value = item.get(key)
            if value:
                names.add(str(value))
    return names


def pull_model(model: str, timeout: int) -> None:
    start_ollama_if_needed(timeout=30)
    if model in installed_models(timeout=10):
        print(f"Model already installed: {model}")
        return
    print(f"Pulling Ollama model: {model}")
    print("This can download several GB and may take a while.")
    run(["ollama", "pull", model], timeout=timeout)


def check(model: str, timeout: int) -> None:
    exe = ollama_exe()
    if not exe:
        raise SystemExit("Ollama is not installed.")
    run([exe, "--version"], timeout=30)
    start_ollama_if_needed(timeout=30)
    models = installed_models(timeout=timeout)
    if model not in models:
        raise SystemExit(f"Ollama is running, but model '{model}' is missing. Run: python scripts/setup_ollama.py --pull")
    print(f"Ollama ready with model: {model}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install/check Ollama and pull the local model used by import review.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--install", action="store_true", help="Install Ollama if it is missing.")
    parser.add_argument("--pull", action="store_true", help="Pull the configured model.")
    parser.add_argument("--check-only", action="store_true", help="Only verify Ollama and the model.")
    parser.add_argument("--timeout", type=int, default=1800, help="Model pull timeout in seconds.")
    args = parser.parse_args()

    if args.install:
        install_ollama()
    if args.pull:
        pull_model(args.model, timeout=args.timeout)
    if args.check_only or not (args.install or args.pull):
        check(args.model, timeout=10)

    print("Ollama setup complete.")


if __name__ == "__main__":
    main()
