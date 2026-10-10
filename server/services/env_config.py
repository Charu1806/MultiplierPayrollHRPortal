"""Load project `.env` into os.environ (no python-dotenv dependency)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_LOADED = False


def load_dotenv(path: Path | None = None) -> None:
    global _LOADED
    if _LOADED:
        return
    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        _LOADED = True
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value
    _LOADED = True


def env(name: str, default: str = "") -> str:
    load_dotenv()
    return (os.environ.get(name) or default).strip()
