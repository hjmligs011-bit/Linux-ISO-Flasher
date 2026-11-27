"""Leitura em fluxo (streaming) de imagens cruas e comprimidas.

Nunca carregamos a imagem inteira em memória: os chunks são entregues ao
mecanismo de gravação conforme são descomprimidos.
"""

from __future__ import annotations

import gzip
import lzma
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..core.errors import ImageError
from ..core.models import ImageInfo


@contextmanager
def open_image_stream(info: ImageInfo) -> Iterator[Iterator[bytes]]:
    """Abre um iterador de chunks de bytes da imagem já descomprimida."""
    path: Path = info.path
    try:
        if info.container == "xz":
            with lzma.open(path, "rb") as handle:
                yield _iter_handle(handle)
        elif info.container == "gz":
            with gzip.open(path, "rb") as handle:
                yield _iter_handle(handle)
        elif info.container == "zst":
            with _open_zstd(path) as chunks:
                yield chunks
        else:
            with path.open("rb") as handle:
                yield _iter_handle(handle)
    except ImageError:
        raise
    except (OSError, EOFError, lzma.LZMAError, gzip.BadGzipFile) as exc:
        raise ImageError(f"Erro ao ler a imagem: {exc}") from exc


def _iter_handle(handle, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    while True:
        chunk = handle.read(chunk_size)
        if not chunk:
            break
        yield chunk


@contextmanager
def _open_zstd(path: Path) -> Iterator[Iterator[bytes]]:
    try:
        from compression import zstd  # Python 3.14+
    except ImportError:
        zstd = None  # type: ignore[assignment]

    if zstd is not None:
        with zstd.open(path, "rb") as handle:
            yield _iter_handle(handle)
        return

    # Fallback para Python sem compression.zstd: binário oficial do zstd,
    # sempre com lista de argumentos (nunca shell=True nem interpolação).
    process = subprocess.Popen(
        ["zstd", "-q", "-d", "-c", "--", str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None

    def chunks() -> Iterator[bytes]:
        while True:
            data = process.stdout.read(1024 * 1024)
            if not data:
                break
            yield data
        code = process.wait()
        if code != 0:
            detail = process.stderr.read(512).decode("utf-8", "replace").strip()
            raise ImageError(f"Erro ao descomprimir zstd: {detail or f'código {code}'}")

    try:
        yield chunks()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
