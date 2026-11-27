"""Motor de gravação: write -> fsync -> verificação byte a byte.

Toda decisão de segurança (identidade, capacidade, cancelamento) acontece aqui e
também no helper; a interface apenas consome ``FlashProgress``/``FlashResult``.
"""

from __future__ import annotations

from ..core.i18n import tr as _

import hashlib
import threading
import time
from collections.abc import Callable

from ..core.errors import (
    CancelledError,
    DeviceChangedError,
    FlasherError,
    ImageError,
    ImageTooLargeError,
    VerificationError,
    WriteError,
)
from ..core.models import FlashProgress, FlashResult, ImageInfo
from ..images.reader import open_image_stream
from ..utils.logging import get_logger
from ..verification.verifier import IntegrityVerifier
from .targets import FlashTarget

log = get_logger("flashing")

ProgressCallback = Callable[[FlashProgress], None]


class FlashController:
    """Executa uma gravação de forma incremental e cancelável."""

    def __init__(
        self,
        image: ImageInfo,
        target: FlashTarget,
        *,
        verify: bool = True,
        chunk_size: int = 1024 * 1024,
        cancel: threading.Event | None = None,
    ) -> None:
        self.image = image
        self.target = target
        self.verify = verify
        self.chunk_size = max(64 * 1024, min(16 * 1024 * 1024, chunk_size))
        self.cancel = cancel or threading.Event()

    def run(self, on_progress: ProgressCallback | None = None) -> FlashResult:
        started = time.monotonic()
        written = 0
        stream_hash = hashlib.sha256()
        total = self.image.uncompressed_size or self.image.size

        try:
            self._raise_if_cancelled()
            expected = self.image.uncompressed_size
            if expected is not None and expected > self.target.identity.size:
                raise ImageTooLargeError(
                    "A imagem descomprimida é maior que a capacidade do dispositivo."
                )

            self.target.prepare()
            # Revalidação imediatamente antes da primeira escrita.
            self.target.verify_identity()

            log.info(
                "Gravando %s em %s (%s bytes)",
                self.image.path.name,
                self.target.identity.devpath,
                total,
            )
            written = self._write_pass(on_progress, total, stream_hash)
            self.target.sync()

            verified = False
            if self.verify:
                verifier = IntegrityVerifier(
                    self.image,
                    self.target,
                    chunk_size=self.chunk_size,
                    cancel=self.cancel,
                )
                outcome = verifier.run(written, on_progress)
                verified = outcome.verified
                if stream_hash.hexdigest() != outcome.digest:
                    raise VerificationError(
                        "Os hashes SHA-256 da imagem e do dispositivo não conferem."
                    )

            if on_progress:
                on_progress(
                    FlashProgress(stage="finish", done=total, total=total, message="Concluído")
                )
            return FlashResult(
                success=verified,
                image=self.image,
                device=self.target.identity,
                bytes_written=written,
                duration=time.monotonic() - started,
                sha256=stream_hash.hexdigest(),
                verified=verified,
            )
        except CancelledError:
            return FlashResult(
                success=False,
                image=self.image,
                device=self.target.identity,
                bytes_written=written,
                duration=time.monotonic() - started,
                sha256=stream_hash.hexdigest(),
                verified=False,
                error="Operação cancelada pelo usuário.",
                cancelled=True,
            )
        except FlasherError as exc:
            log.error("Falha na gravação: %s", exc)
            return FlashResult(
                success=False,
                image=self.image,
                device=self.target.identity,
                bytes_written=written,
                duration=time.monotonic() - started,
                sha256=stream_hash.hexdigest(),
                verified=False,
                error=str(exc),
            )
        except (OSError, RuntimeError, ValueError) as exc:
            log.exception("Erro inesperado na gravação")
            return FlashResult(
                success=False,
                image=self.image,
                device=self.target.identity,
                bytes_written=written,
                duration=time.monotonic() - started,
                sha256=stream_hash.hexdigest(),
                verified=False,
                error=f"Falha na gravação: {exc}",
            )
        finally:
            try:
                self.target.close()
            except OSError:
                pass

    # ------------------------------------------------------------------ etapas
    def _raise_if_cancelled(self) -> None:
        if self.cancel.is_set():
            raise CancelledError()

    def _write_pass(
        self, on_progress: ProgressCallback | None, total: int, digest
    ) -> int:
        offset = 0
        last_report = 0.0
        write_start = time.monotonic()
        self._write_start_ref = write_start
        with open_image_stream(self.image) as chunks:
            for chunk in chunks:
                self._raise_if_cancelled()
                if offset + len(chunk) > self.target.identity.size:
                    raise ImageTooLargeError(_("A imagem não cabe no dispositivo selecionado."))
                self.target.write(offset, chunk)
                digest.update(chunk)
                offset += len(chunk)
                now = time.monotonic()
                if on_progress is not None and (now - last_report >= 0.1 or offset == total):
                    speed, eta = self._speed(offset, now, total)
                    on_progress(
                        FlashProgress(
                            stage="write",
                            done=offset,
                            total=total,
                            speed=speed,
                            eta=eta,
                            message="Gravando imagem…",
                        )
                    )
                    last_report = now
        if offset == 0:
            raise ImageError(_("A imagem não continha dados."))
        self.target.sync()
        return offset

    def _speed(self, done: int, now: float, total: int) -> tuple[float, float | None]:
        elapsed = now - self._write_start_ref
        if elapsed < 0.1:
            return 0.0, None
        speed = done / elapsed
        eta = (total - done) / speed if speed > 0 else None
        return speed, max(0.0, eta) if eta is not None else None
