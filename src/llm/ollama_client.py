from __future__ import annotations

import os
from typing import Any


def build_ollama_options(task: str | None = None, default_num_predict: int | None = None) -> dict[str, Any]:
    """Build stable Ollama generation options from environment variables.

    The default keeps generation CPU-only. That is slower, but avoids low-VRAM
    CUDA failures on machines where Ollama tries to offload too much by default.
    Set MIAGE_OLLAMA_NUM_GPU=-1 or another Ollama-supported value to re-enable GPU offload.
    """
    options: dict[str, Any] = {}
    temperature = _env_float("TEMPERATURE", task=task, default=0.0)
    if temperature is not None:
        options["temperature"] = temperature

    num_gpu = _env_int("NUM_GPU", task=task, default=0)
    if num_gpu is not None:
        options["num_gpu"] = num_gpu

    num_ctx = _env_int("NUM_CTX", task=task, default=2048)
    if num_ctx is not None:
        options["num_ctx"] = num_ctx

    num_predict = _env_int("NUM_PREDICT", task=task, default=default_num_predict)
    if num_predict is not None:
        options["num_predict"] = num_predict

    return options


def _env_int(name: str, task: str | None, default: int | None = None) -> int | None:
    raw = _env_value(name, task=task)
    if raw is None:
        return default
    if raw == "":
        return None
    return int(raw)


def _env_float(name: str, task: str | None, default: float | None = None) -> float | None:
    raw = _env_value(name, task=task)
    if raw is None:
        return default
    if raw == "":
        return None
    return float(raw)


def _env_value(name: str, task: str | None) -> str | None:
    keys = []
    if task:
        keys.append(f"MIAGE_OLLAMA_{task.upper()}_{name}")
    keys.append(f"MIAGE_OLLAMA_{name}")
    for key in keys:
        if key in os.environ:
            value = os.environ[key].strip()
            if value.lower() == "auto":
                return ""
            return value
    return None
