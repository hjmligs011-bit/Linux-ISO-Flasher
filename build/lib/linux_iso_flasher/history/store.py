"""Persistência atômica do histórico em ``$XDG_STATE_HOME``.

O histórico registra apenas metadados; nenhum dado de imagem é copiado.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.config import state_home
from ..core.models import FlashResult, HistoryEntry
from ..utils.logging import get_logger

log = get_logger("history")


def history_path() -> Path:
    return state_home() / "linux-iso-flasher" / "history.json"


class HistoryStore:
    """Leitura/escrita segura do histórico (limite configurável)."""

    def __init__(self, path: Path | None = None, limit: int = 100) -> None:
        self.path = path or history_path()
        self.limit = limit

    def load(self) -> list[HistoryEntry]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            entries = [HistoryEntry.from_dict(item) for item in data if isinstance(item, dict)]
            return sorted(entries, key=lambda e: e.timestamp, reverse=True)[: self.limit]
        except (OSError, ValueError, KeyError, TypeError):
            return []

    def add(self, result: FlashResult) -> HistoryEntry:
        entry = HistoryEntry(
            timestamp=result.timestamp,
            image_name=result.image.name,
            image_path=str(result.image.path),
            image_size=result.image.size,
            device=result.device.name,
            device_id=result.device.id,
            device_sysname=result.device.sysname,
            duration=result.duration,
            verified=result.verified,
            success=result.success,
            error=result.error,
            sha256=result.sha256,
        )
        entries = [entry, *self.load()]
        self._write([item.to_dict() for item in entries[: self.limit]])
        return entry

    def clear(self) -> None:
        self._write([])

    def _write(self, data: list[dict[str, Any]]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("Não foi possível salvar histórico: %s", exc)
