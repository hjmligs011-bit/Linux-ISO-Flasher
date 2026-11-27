"""Modelos de dados imutáveis usados entre os módulos.

Nenhum modelo contém dados simulados: todos os campos são preenchidos a partir
de UDisks2/sysfs ou do arquivo de imagem selecionado pelo usuário.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class ImageInfo:
    """Metadados validados de uma imagem selecionada."""

    path: Path
    size: int
    fmt: str                       # iso | img | raw | bin | xz | gz | zst
    container: str | None          # xz | gz | zst | None
    uncompressed_size: int | None  # quando conhecido pelo cabeçalho/rodapé
    sha256: str | None = None      # preenchido sob demanda

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def display_format(self) -> str:
        if self.container:
            return f"{self.fmt} (comprimida em {self.container.upper()})"
        return self.fmt.upper()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "name": self.name,
            "size": self.size,
            "format": self.fmt,
            "container": self.container,
            "uncompressed_size": self.uncompressed_size,
        }


@dataclass(frozen=True)
class PartitionInfo:
    """Partição existente em um dispositivo de destino."""

    number: int
    label: str
    filesystem: str
    size: int
    mount_points: tuple[str, ...]

    @property
    def description(self) -> str:
        parts = [f"Partição {self.number}"]
        if self.label:
            parts.append(self.label)
        if self.filesystem and self.filesystem != "unknown":
            parts.append(self.filesystem.upper())
        return " · ".join(parts)


@dataclass(frozen=True)
class DeviceIdentity:
    """Identidade estável de um dispositivo de bloco.

    O ``fingerprint`` é recalculado imediatamente antes da gravação e compare
    com o valor selecionado na interface, protegendo contra troca de dispositivo
    (replug em outra porta, por exemplo).
    """

    sysname: str
    syspath: str
    devpath: str
    size: int
    major: int
    minor: int
    vendor: str
    model: str
    serial: str
    transport: str
    removable: bool
    media: str = ""

    @property
    def fingerprint(self) -> str:
        # sysname/syspath não entram: o mesmo dispositivo pode mudar de nome.
        stable = {
            "vendor": self.vendor.strip(),
            "model": self.model.strip(),
            "serial": self.serial.strip(),
            "size": self.size,
            "transport": self.transport.strip(),
            "media": self.media.strip(),
        }
        payload = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()

    @property
    def id(self) -> str:
        return self.serial.strip() or self.syspath or self.sysname

    @property
    def name(self) -> str:
        return " ".join(p for p in (self.vendor, self.model) if p).strip() or self.sysname

    def to_dict(self) -> dict[str, Any]:
        return {
            "sysname": self.sysname,
            "syspath": self.syspath,
            "devpath": self.devpath,
            "size": self.size,
            "major": self.major,
            "minor": self.minor,
            "vendor": self.vendor,
            "model": self.model,
            "serial": self.serial,
            "transport": self.transport,
            "removable": self.removable,
            "media": self.media,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class DeviceInfo:
    """Dispositivo removível detectado, pronto para exibição."""

    identity: DeviceIdentity
    partitions: tuple[PartitionInfo, ...] = ()
    available: int | None = None
    connection: str = ""
    system_disk: bool = False

    @property
    def safe(self) -> bool:
        return self.identity.removable and not self.system_disk

    @property
    def display_name(self) -> str:
        return self.identity.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "partitions": [
                {
                    "number": p.number,
                    "label": p.label,
                    "filesystem": p.filesystem,
                    "size": p.size,
                    "mount_points": list(p.mount_points),
                }
                for p in self.partitions
            ],
            "available": self.available,
            "connection": self.connection,
            "system_disk": self.system_disk,
        }


@dataclass(frozen=True)
class FlashProgress:
    """Estado de progresso emitido pelo mecanismo de gravação."""

    stage: str                 # prepare | write | verify | finish
    done: int
    total: int
    speed: float = 0.0
    eta: float | None = None
    message: str = ""

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return min(100.0, max(0.0, self.done * 100.0 / self.total))


@dataclass(frozen=True)
class FlashResult:
    """Resultado final de uma operação (sucesso implica verificação aprovada)."""

    success: bool
    image: ImageInfo
    device: DeviceIdentity
    bytes_written: int
    duration: float
    sha256: str | None
    verified: bool
    error: str | None = None
    cancelled: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

    def to_history_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(timespec="seconds"),
            "image_name": self.image.name,
            "image_path": str(self.image.path),
            "image_size": self.image.size,
            "device": self.device.name,
            "device_id": self.device.id,
            "device_sysname": self.device.sysname,
            "duration": round(self.duration, 2),
            "verified": self.verified,
            "success": self.success,
            "error": self.error,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class HistoryEntry:
    timestamp: datetime
    image_name: str
    image_path: str
    image_size: int
    device: str
    device_id: str
    device_sysname: str
    duration: float
    verified: bool
    success: bool
    error: str | None = None
    sha256: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryEntry:
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            image_name=data.get("image_name", ""),
            image_path=data.get("image_path", ""),
            image_size=int(data.get("image_size", 0)),
            device=data.get("device", ""),
            device_id=data.get("device_id", ""),
            device_sysname=data.get("device_sysname", ""),
            duration=float(data.get("duration", 0)),
            verified=bool(data.get("verified", False)),
            success=bool(data.get("success", False)),
            error=data.get("error"),
            sha256=data.get("sha256"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(timespec="seconds"),
            "image_name": self.image_name,
            "image_path": self.image_path,
            "image_size": self.image_size,
            "device": self.device,
            "device_id": self.device_id,
            "device_sysname": self.device_sysname,
            "duration": self.duration,
            "verified": self.verified,
            "success": self.success,
            "error": self.error,
            "sha256": self.sha256,
        }
