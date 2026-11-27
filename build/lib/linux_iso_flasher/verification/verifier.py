"""Verificador de integridade.

Reabre a imagem (descomprimindo-a novamente) e compara cada chunk com os dados
lidos do dispositivo. Também calcula o SHA-256 dos dados lidos, permitindo
comparar com o hash calculado durante a gravação.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from ..core.errors import CancelledError, VerificationError
from ..core.models import FlashProgress, ImageInfo
from ..flashing.targets import FlashTarget
from ..images.reader import open_image_stream

ProgressCallback = Callable[[FlashProgress], None]


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    bytes_checked: int
    digest: str


class IntegrityVerifier:
    """Compara imagem original e destino byte a byte, em fluxo."""

    def __init__(
        self,
        image: ImageInfo,
        target: FlashTarget,
        *,
        chunk_size: int = 1024 * 1024,
        cancel: threading.Event | None = None,
    ) -> None:
        self.image = image
        self.target = target
        self.chunk_size = max(64 * 1024, min(16 * 1024 * 1024, chunk_size))
        self.cancel = cancel or threading.Event()

    def run(
        self, expected_bytes: int | None = None, on_progress: ProgressCallback | None = None
    ) -> VerificationResult:
        digest = hashlib.sha256()
        offset = 0
        started = time.monotonic()
        last_report = 0.0
        total = self.image.uncompressed_size or expected_bytes or self.image.size

        with open_image_stream(self.image) as chunks:
            for chunk in chunks:
                if self.cancel.is_set():
                    raise CancelledError()
                stored = self.target.read(offset, len(chunk))
                if stored != chunk:
                    raise VerificationError(
                        "Os dados gravados divergem da imagem original."
                    )
                digest.update(stored)
                offset += len(chunk)

                now = time.monotonic()
                if on_progress is not None and (
                    now - last_report >= 0.1
                    or (expected_bytes is not None and offset >= expected_bytes)
                ):
                    elapsed = max(0.05, now - started)
                    speed = offset / elapsed
                    eta = (total - offset) / speed if speed > 0 else None
                    on_progress(
                        FlashProgress(
                            stage="verify",
                            done=offset,
                            total=total,
                            speed=speed,
                            eta=eta,
                            message="Verificando dados gravados…",
                        )
                    )
                    last_report = now

        if expected_bytes is not None and offset != expected_bytes:
            raise VerificationError(
                "A quantidade de dados verificada é diferente da gravada."
            )
        return VerificationResult(True, offset, digest.hexdigest())
