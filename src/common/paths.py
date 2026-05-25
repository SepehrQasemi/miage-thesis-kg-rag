import os
from pathlib import Path

_ENV_LOADED = False


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_env_file() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    env_file = project_root() / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(env_file, override=False)


def _path_from_env(env_name: str, fallback: Path) -> Path:
    load_env_file()
    value = os.environ.get(env_name)
    if not value:
        return fallback
    path = Path(value)
    return path if path.is_absolute() else project_root() / path


def data_dir() -> Path:
    return _path_from_env("MIAGE_DATA_DIR", project_root() / "data")


def db_path() -> Path:
    return _path_from_env("MIAGE_APP_DB", data_dir() / "app.sqlite")


def raw_pdf_dir() -> Path:
    return _path_from_env("MIAGE_RAW_PDF_DIR", data_dir() / "raw" / "theses_pdf")


def processed_dir() -> Path:
    return _path_from_env("MIAGE_PROCESSED_DIR", data_dir() / "processed")


def reports_dir() -> Path:
    return _path_from_env("MIAGE_REPORTS_DIR", data_dir() / "reports")


def graph_dir() -> Path:
    return _path_from_env("MIAGE_GRAPH_DIR", data_dir() / "graph")


def cache_dir() -> Path:
    return _path_from_env("MIAGE_CACHE_DIR", data_dir() / "cache")


def staging_dir() -> Path:
    return _path_from_env("MIAGE_STAGING_DIR", data_dir() / "staging")
