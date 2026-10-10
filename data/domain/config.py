"""Loads /config/*.json — the single place business constants come from.

DATASET=acme (default) uses config/*.json.
DATASET=alt uses config/alt/*.json and seed/alt.json when present.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def dataset_name() -> str:
    return (os.environ.get("DATASET") or "acme").strip().lower()


def _config_root() -> Path:
    name = dataset_name()
    if name == "alt":
        return CONFIG_DIR / "alt"
    return CONFIG_DIR


@lru_cache(maxsize=None)
def _load(name: str) -> Dict[str, Any]:
    root = _config_root()
    path = root / name
    if not path.exists() and root != CONFIG_DIR:
        path = CONFIG_DIR / name
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def cycle_config() -> Dict[str, Any]:
    return _load("cycle.json")


def rules_config() -> Dict[str, Any]:
    return _load("rules.json")


def seed_config() -> Dict[str, Any]:
    if dataset_name() == "alt":
        alt_seed = ROOT / "seed" / "alt.json"
        if alt_seed.exists():
            with open(alt_seed, encoding="utf-8") as fh:
                return json.load(fh)
        alt_cfg = CONFIG_DIR / "alt" / "seed.json"
        if alt_cfg.exists():
            with open(alt_cfg, encoding="utf-8") as fh:
                return json.load(fh)
    return _load("seed.json")


def company_config() -> Dict[str, Any]:
    return _load("company.json")


def reload() -> None:
    _load.cache_clear()
