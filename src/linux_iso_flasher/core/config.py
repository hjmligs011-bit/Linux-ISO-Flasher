"""Configuração persistente do usuário (XDG)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "theme": "dark",          # dark | light | system
    "language": "pt_BR",      # pt_BR | en
    "verify": True,
    "chunk_size": 1024 * 1024,
    "history_limit": 100,
    "last_image_dir": "",
}


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def state_home() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))


def cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))


def config_path() -> Path:
    return config_home() / "linux-iso-flasher" / "config.json"


def load_config() -> dict[str, Any]:
    config = dict(DEFAULTS)
    path = config_path()
    try:
        if path.is_file():
            stored = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                for key in DEFAULTS:
                    if key in stored:
                        config[key] = stored[key]
    except (OSError, ValueError):
        pass
    if config["theme"] not in ("dark", "light", "system"):
        config["theme"] = DEFAULTS["theme"]
    if config["language"] not in ("pt_BR", "en"):
        config["language"] = DEFAULTS["language"]
    try:
        config["chunk_size"] = max(64 * 1024, min(16 * 1024 * 1024, int(config["chunk_size"])))
    except (TypeError, ValueError):
        config["chunk_size"] = DEFAULTS["chunk_size"]
    config["verify"] = bool(config["verify"])
    return config


def save_config(config: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
