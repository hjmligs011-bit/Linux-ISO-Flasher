"""Execução do helper privilegiado via ``pkexec``.

A interface gráfica nunca roda como root. Toda operação sobre dispositivos de
bloco acontece em um processo separado, iniciado por pkexec e autorizado por
uma ação Polkit específica. O diagrama de confiança é:

    GUI (usuário) --JSON--> pkexec --JSON--> helper (root)
                  <--progresso/resultado--

O helper valida novamente tudo o que recebe; a GUI nunca constrói comandos de
shell e nunca interpreta dispositivos sem confirmação do usuário.
"""

from __future__ import annotations

from ..core.i18n import tr as _

import json
import os
import queue
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from ..core.errors import CancelledError, HelperError, PermissionErrorFlasher
from ..utils.logging import get_logger

log = get_logger("permissions")

DEFAULT_HELPER = Path("/usr/libexec/linux-iso-flasher/helper")


def helper_candidates() -> list[Path]:
    candidates: list[Path] = []
    env = os.environ.get("LIF_HELPER")
    if env:
        candidates.append(Path(env))
    candidates.append(DEFAULT_HELPER)
    repo = Path(__file__).resolve().parents[3] / "src/linux_iso_flasher/flashing/helper_entry.py"
    candidates.append(repo)
    return candidates


def find_helper() -> Path | None:
    for path in helper_candidates():
        if path.is_file() and os.access(path, os.R_OK):
            return path
    return None


class HelperLauncher:
    """Cliente do protocolo JSON-lines do helper privilegiado."""

    def __init__(self, helper_path: Path | None = None, use_pkexec: bool = True) -> None:
        self.helper_path = helper_path or find_helper()
        self.use_pkexec = use_pkexec

    @property
    def available(self) -> bool:
        if self.helper_path is None or not self.helper_path.is_file():
            return False
        return not self.use_pkexec or shutil.which("pkexec") is not None

    def flash(
        self,
        request: dict,
        on_progress: Callable[[dict], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> dict:
        """Executa a gravação e retorna o dicionário de resultado do helper."""
        if not self.available or self.helper_path is None:
            raise HelperError(_("Helper privilegiado não encontrado nesta instalação."))

        command = (
            [shutil.which("pkexec") or "pkexec", str(self.helper_path)]
            if self.use_pkexec
            else [str(self.helper_path)]
        )
        log.info("Iniciando helper: %s", "pkexec " + str(self.helper_path))
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as exc:
            raise HelperError(f"Não foi possível iniciar o helper: {exc}") from exc

        try:
            messages: queue.Queue[dict | None] = queue.Queue()
            errors: list[str] = []

            def read_stdout() -> None:
                assert process.stdout is not None
                for line in process.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        messages.put(json.loads(line))
                    except json.JSONDecodeError:
                        errors.append(f"Resposta inválida do helper: {line[:200]}")
                messages.put(None)

            def read_stderr() -> None:
                assert process.stderr is not None
                for line in process.stderr:
                    text = line.strip()
                    if text:
                        log.debug("helper stderr: %s", text)
                        errors.append(text)

            threading.Thread(target=read_stdout, daemon=True).start()
            threading.Thread(target=read_stderr, daemon=True).start()

            assert process.stdin is not None
            try:
                process.stdin.write(json.dumps({"type": "start", "request": request}) + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                process.kill()
                raise PermissionErrorFlasher(
                    "A autenticação administrativa foi cancelada ou não concedida."
                ) from exc

            result: dict | None = None
            cancelled_sent = False
            pending = object()
            while True:
                try:
                    message = messages.get(timeout=0.15)
                except queue.Empty:
                    message = pending  # type: ignore[assignment]
                if message is None:
                    break
                if message is pending:
                    if cancel is not None and cancel.is_set() and not cancelled_sent:
                        try:
                            process.stdin.write('{"type":"cancel"}\n')
                            process.stdin.flush()
                            cancelled_sent = True
                        except (BrokenPipeError, OSError):
                            pass
                    if process.poll() is not None and messages.empty():
                        break
                    continue
                kind = message.get("type")
                if kind == "progress":
                    if on_progress is not None:
                        on_progress(message)
                elif kind == "result":
                    result = message.get("result")
                elif kind == "error":
                    raise HelperError(str(message.get("message") or "Falha no helper."))
                elif kind == "auth_failed":
                    raise PermissionErrorFlasher(
                        "Permissão administrativa negada. A gravação não foi iniciada."
                    )

            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise HelperError(_("O helper não encerrou após a operação."))

            if cancel is not None and cancel.is_set():
                raise CancelledError()
            if result is not None:
                return result
            if process.returncode == 127:
                raise PermissionErrorFlasher(_("Polkit não autorizou a execução do helper."))
            detail = errors[-1] if errors else ""
            raise HelperError(detail or f"Helper terminou com código {process.returncode}.")
        finally:
            self._close_pipes(process)

    @staticmethod
    def _close_pipes(process: subprocess.Popen) -> None:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass
