"""Detecção de formato, validação e estimativa de tamanho de imagens.

A detecção usa assinatura de bytes (magic numbers) e extensão. Um arquivo só é
aceito se a assinatura confirmar o formato compressivo; imagens cruas precisam
ter extensão conhecida e conteúdo não vazio.
"""

from __future__ import annotations

from ..core.i18n import tr as _

import gzip
import os
import struct
from pathlib import Path

from ..core.errors import ImageError, ImageNotFoundError, UnsupportedFormatError
from ..core.models import ImageInfo

RAW_FORMATS = ("iso", "img", "raw", "bin")
COMPRESSED_FORMATS = ("xz", "gz", "zst")
SUPPORTED_EXTENSIONS = RAW_FORMATS + COMPRESSED_FORMATS

# Arquivos comprimidos até este tamanho são validados por completo antes da
# gravação (detecta corrupção e fornece tamanho exato). Acima disso, usamos
# metadados do formato e a verificação pós-gravação continua obrigatória.
FULL_SCAN_LIMIT = 512 * 1024 * 1024

_MAGIC = {
    b"\xfd7zXZ\x00": "xz",
    b"\x1f\x8b": "gz",
    b"\x28\xb5\x2f\xfd": "zst",
}


def _read_head(path: Path, size: int = 64 * 1024) -> bytes:
    with path.open("rb") as handle:
        return handle.read(size)


def _compressor_from_magic(head: bytes) -> str | None:
    for magic, name in _MAGIC.items():
        if head.startswith(magic):
            return name
    return None


def _gz_uncompressed_size(path: Path) -> int | None:
    """ISIZE do trailer gzip (módulo 2^32)."""
    try:
        with path.open("rb") as handle:
            handle.seek(-4, os.SEEK_END)
            isize = struct.unpack("<I", handle.read(4))[0]
        return isize if isize else None
    except OSError:
        return None


def _zst_uncompressed_size(path: Path, head: bytes) -> int | None:
    try:
        from compression import zstd  # Python 3.14+
    except ImportError:
        return None
    try:
        info = zstd.get_frame_info(head)
        size = int(info.frame_content_size)
        return size if 0 < size < 2**63 else None
    except Exception:
        return None


def _scan_stream(path: Path, container: str, size: int) -> int:
    """Descomprime o fluxo inteiro em chunks, contando bytes e validando CRC."""
    from .reader import open_image_stream

    probe = ImageInfo(
        path=path, size=size, fmt="iso", container=container, uncompressed_size=None
    )
    total = 0
    with open_image_stream(probe) as chunks:
        for chunk in chunks:
            total += len(chunk)
    return total


def inspect_image(path: Path | str) -> ImageInfo:
    """Valida ``path`` e retorna seus metadados; levanta ``ImageError`` se inválido."""
    candidate = Path(path).expanduser()
    if not candidate.exists():
        raise ImageNotFoundError(f"Arquivo não encontrado: {candidate.name}")
    if not candidate.is_file():
        raise ImageError(_("O caminho selecionado não é um arquivo regular."))
    try:
        stat = candidate.stat()
    except OSError as exc:
        raise ImageError(f"Não foi possível ler o arquivo: {exc.strerror or exc}") from exc
    if stat.st_size == 0:
        raise ImageError(_("A imagem selecionada está vazia."))

    head = _read_head(candidate)
    magic = _compressor_from_magic(head)

    suffixes = [suffix.lower().lstrip(".") for suffix in candidate.suffixes]
    extension = suffixes[-1] if suffixes else ""
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFormatError(
            "Use uma imagem .iso, .img, .raw, .bin ou comprimida em .xz, .gz, .zst."
        )

    container = magic
    if magic is None and extension in COMPRESSED_FORMATS:
        raise ImageError(_("O arquivo comprimido não possui uma assinatura válida."))

    if container:
        fmt = "iso"
        for suffix in suffixes[:-1]:
            if suffix in RAW_FORMATS:
                fmt = suffix
                break

        if stat.st_size <= FULL_SCAN_LIMIT:
            try:
                uncompressed = _scan_stream(candidate, container, stat.st_size)
            except ImageError:
                raise
            except Exception as exc:
                raise ImageError(f"A imagem comprimida está corrompida: {exc}") from exc
        else:
            uncompressed = None
            if container == "gz":
                uncompressed = _gz_uncompressed_size(candidate)
            elif container == "zst":
                uncompressed = _zst_uncompressed_size(candidate, head)
            # xz não expõe o tamanho no rodapé: capacidade é conferida na gravação.
    else:
        fmt = extension
        uncompressed = stat.st_size

    return ImageInfo(
        path=candidate.resolve(),
        size=stat.st_size,
        fmt=fmt,
        container=container,
        uncompressed_size=uncompressed,
    )
