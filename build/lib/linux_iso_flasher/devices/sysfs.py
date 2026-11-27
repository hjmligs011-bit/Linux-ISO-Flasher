"""Leitura direta de atributos de dispositivos de bloco em /sys.

Nenhuma informação é inventada: se o atributo não existir, o campo fica vazio
e a interface mostra ``—``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from ..core.errors import DeviceError, DeviceNotFoundError
from ..core.models import DeviceIdentity

SYSNAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SECTOR_SIZE = 512


def validate_sysname(sysname: str) -> str:
    """Impede path traversal antes de montar qualquer caminho em /sys."""
    if not SYSNAME_RE.fullmatch(sysname or "") or sysname in (".", ".."):
        raise DeviceError(f"Nome de dispositivo inválido: {sysname!r}")
    return sysname


def block_path(sysname: str, sysroot: str | Path = "/sys") -> Path:
    name = validate_sysname(sysname)
    return Path(sysroot) / "block" / name


def _read(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default


def _int_from(path: Path, default: int = 0) -> int:
    value = _read(path)
    try:
        return int(value, 0)
    except ValueError:
        return default


def identity_from_sysfs(sysname: str, sysroot: str | Path = "/sys") -> DeviceIdentity:
    """Constrói a identidade a partir de sysfs; falha se o dispositivo sumiu."""
    name = validate_sysname(sysname)
    base = block_path(name, sysroot)
    if not base.exists():
        raise DeviceNotFoundError(f"Dispositivo {name} não encontrado em sysfs.")

    sectors = _int_from(base / "size")
    dev = _read(base / "dev")
    try:
        major_s, minor_s = dev.split(":")
        major, minor = int(major_s), int(minor_s)
    except (ValueError, AttributeError) as exc:
        raise DeviceError(f"Não foi possível identificar {name}.") from exc

    devdir = base / "device"
    vendor = _read(devdir / "vendor")
    model = _read(devdir / "model")
    serial = _read(devdir / "serial") or _read(devdir / "uid")
    transport = _read(devdir / "transport")
    media = _read(base / "queue" / "rotational") and "rotational" or ""

    if not transport:
        # inferência conservadora pelo caminho do dispositivo, sem inventar modelo
        resolved = str(devdir.resolve()) if devdir.exists() else ""
        lowered = resolved.lower()
        for candidate in ("usb", "sdio", "mmc", "nvme", "ata", "scsi", "virtio"):
            if candidate in lowered:
                transport = candidate
                break

    removable = _read(base / "removable") == "1"
    devpath = f"/dev/{name}"

    return DeviceIdentity(
        sysname=name,
        syspath=str(base.resolve()),
        devpath=devpath,
        size=sectors * SECTOR_SIZE,
        major=major,
        minor=minor,
        vendor=vendor,
        model=model,
        serial=serial,
        transport=transport,
        removable=removable,
        media=media,
    )


def is_usb_or_card(identity: DeviceIdentity) -> bool:
    """True apenas para transportes típicos de mídia removível externa."""
    return identity.transport.lower() in {
        "usb", "sdio", "mmc", "ieee1394", "firewire", "scsi"
    }


def system_device_ids() -> set[tuple[int, int]]:
    """Major:minor de dispositivos que montam o sistema em execução."""
    ids: set[tuple[int, int]] = set()
    for mountpoint in ("/", "/boot", "/boot/efi", "/usr", "/var", "/etc", "/home"):
        try:
            st = os.stat(mountpoint)
        except OSError:
            continue
        major = os.major(st.st_dev)
        minor = os.minor(st.st_dev)
        if major or minor:
            ids.add((major, minor))
    return ids


def is_system_device(identity: DeviceIdentity) -> bool:
    return (identity.major, identity.minor) in system_device_ids()


def block_is_partition(sysname: str, sysroot: str | Path = "/sys") -> bool:
    return (block_path(sysname, sysroot) / "partition").exists()
