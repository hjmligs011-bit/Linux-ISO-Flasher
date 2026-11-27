"""Abstrações de destino de gravação.

``FileTarget`` existe para testes com arquivos temporários; ``BlockDeviceTarget``
é o único destino usado pelo helper privilegiado e só aceita dispositivos de
bloco reais, validados contra sysfs.
"""

from __future__ import annotations

from ..core.i18n import tr as _

import os
import re
import stat
from abc import ABC, abstractmethod
from pathlib import Path

from ..core.errors import (
    DeviceChangedError,
    DeviceError,
    DeviceNotFoundError,
    UnsafeDeviceError,
    WriteError,
)
from ..core.models import DeviceIdentity
from ..devices.sysfs import (
    block_is_partition,
    identity_from_sysfs,
    is_system_device,
    is_usb_or_card,
    validate_sysname,
)


class FlashTarget(ABC):
    """Interface de escrita/leitura por offsets (sem comandos externos)."""

    def __init__(self, identity: DeviceIdentity) -> None:
        self.identity = identity

    @abstractmethod
    def prepare(self) -> None:
        """Prepara o destino (desmontagem, abertura do descritor)."""

    @abstractmethod
    def write(self, offset: int, data: bytes) -> None:
        """Grava ``data`` exatamente em ``offset``."""

    @abstractmethod
    def read(self, offset: int, size: int) -> bytes:
        """Lê ``size`` bytes exatos em ``offset``."""

    @abstractmethod
    def sync(self) -> None:
        """Sincroniza os dados com o dispositivo."""

    @abstractmethod
    def close(self) -> None:
        """Libera recursOS."""

    def verify_identity(self, expected: DeviceIdentity | None = None) -> None:
        """Confere novamente a identidade do destino antes de gravar."""
        reference = expected or self.identity
        current = identity_from_sysfs(reference.sysname)
        if current.fingerprint != reference.fingerprint:
            raise DeviceChangedError(
                "A identidade do dispositivo mudou desde a seleção; a gravação foi abortada."
            )
        if current.devpath != self.identity.devpath:
            raise DeviceChangedError(_("O caminho do dispositivo mudou; gravação abortada."))
        if current.size < reference.size:
            raise DeviceChangedError(_("O dispositivo ficou menor; gravação abortada."))


class FileTarget(FlashTarget):
    """Destino baseado em arquivo, usado somente em testes automatizados."""

    def __init__(self, path: Path | str, identity: DeviceIdentity | None = None) -> None:
        target = Path(path)
        if identity is None:
            identity = DeviceIdentity(
                sysname=target.name,
                syspath=str(target.parent),
                devpath=str(target),
                size=target.stat().st_size,
                major=0,
                minor=0,
                vendor="",
                model=target.name,
                serial="",
                transport="file",
                removable=True,
            )
        super().__init__(identity)
        self.path = target
        self._fd: int | None = None

    def prepare(self) -> None:
        self._fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)

    def write(self, offset: int, data: bytes) -> None:
        assert self._fd is not None
        written = os.pwrite(self._fd, data, offset)
        if written != len(data):
            raise WriteError(_("Escrita incompleta no arquivo de teste."))

    def read(self, offset: int, size: int) -> bytes:
        assert self._fd is not None
        return os.pread(self._fd, size, offset)

    def sync(self) -> None:
        if self._fd is not None:
            os.fsync(self._fd)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def verify_identity(self, expected: DeviceIdentity | None = None) -> None:
        # Arquivos de teste não têm sysfs; garantimos ao menos que o caminho
        # continua sendo o mesmo arquivo regular.
        if not self.path.is_file():
            raise DeviceNotFoundError(_("Arquivo de teste removido durante a operação."))


class BlockDeviceTarget(FlashTarget):
    """Destino real: dispositivo de bloco verificado no momento da abertura."""

    def __init__(self, identity: DeviceIdentity) -> None:
        super().__init__(identity)
        self._fd: int | None = None

    def prepare(self) -> None:
        current = identity_from_sysfs(self.identity.sysname)
        self.verify_identity(current)
        try:
            info = os.stat(self.identity.devpath)
        except OSError as exc:
            raise DeviceNotFoundError(f"Não foi possível abrir {self.identity.devpath}: {exc}") from exc
        if not stat.S_ISBLK(info.st_mode):
            raise UnsafeDeviceError(_("O destino não é um dispositivo de bloco."))
        if os.major(info.st_rdev) != current.major or os.minor(info.st_rdev) != current.minor:
            raise DeviceChangedError(_("Números major/minor do dispositivo não conferem."))
        self._fd = os.open(self.identity.devpath, os.O_WRONLY | os.O_CLOEXEC | os.O_SYNC)

    def write(self, offset: int, data: bytes) -> None:
        assert self._fd is not None
        view = memoryview(data)
        written_total = 0
        while written_total < len(view):
            written = os.pwrite(self._fd, view[written_total:], offset + written_total)
            if written <= 0:
                raise WriteError(_("O dispositivo não aceitou mais dados (pode estar cheio)."))
            written_total += written

    def read(self, offset: int, size: int) -> bytes:
        # Leitura feita em descritor separado para não depender de O_WRONLY.
        fd = os.open(self.identity.devpath, os.O_RDONLY | os.O_CLOEXEC)
        try:
            chunks: list[bytes] = []
            remaining = size
            position = offset
            while remaining > 0:
                chunk = os.pread(fd, min(remaining, 1024 * 1024), position)
                if not chunk:
                    raise DeviceError(_("Leitura de verificação incompleta."))
                chunks.append(chunk)
                position += len(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)
        finally:
            os.close(fd)

    def sync(self) -> None:
        if self._fd is not None:
            os.fsync(self._fd)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


def assert_safe_target(
    identity: DeviceIdentity, expected_fingerprint: str | None = None
) -> None:
    """Validação de segurança executada no helper antes de qualquer escrita."""
    name = validate_sysname(identity.sysname)
    if block_is_partition(name):
        raise UnsafeDeviceError(_("A seleção aponta para uma partição, não para o disco inteiro."))
    if not identity.removable and not is_usb_or_card(identity):
        raise UnsafeDeviceError(_("Disco interno bloqueado por padrão."))
    if is_system_device(identity):
        raise UnsafeDeviceError(_("Este dispositivo contém o sistema em execução."))
    if identity.size <= 0:
        raise DeviceError(_("Capacidade do dispositivo inválida."))
    if expected_fingerprint is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", expected_fingerprint or ""):
            raise DeviceChangedError(_("Identidade esperada inválida."))
        if identity.fingerprint != expected_fingerprint:
            raise DeviceChangedError(_("A identidade do dispositivo não confere com a seleção."))
    try:
        mode = os.stat(identity.devpath).st_mode
    except OSError as exc:
        raise DeviceNotFoundError(_("Dispositivo não encontrado.")) from exc
    if not stat.S_ISBLK(mode):
        raise UnsafeDeviceError(_("O destino precisa ser um dispositivo de bloco."))


__all__ = [
    "FlashTarget",
    "FileTarget",
    "BlockDeviceTarget",
    "assert_safe_target",
]
