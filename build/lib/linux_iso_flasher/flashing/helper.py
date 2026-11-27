"""Helper privilegiado: único código que escreve em dispositivos de bloco.

Segurança:
  * recebe somente um pedido JSON com campos estritamente validados;
  * nunca executa shells nem constrói comandos com dados externos;
  * revalida a identidade do dispositivo e o tipo de destino;
  * bloqueia discos internos e dispositivos que montam o sistema;
  * desmonta partições via UDisks2 antes de gravar;
  * reporta progresso e resultado por JSON-lines.
"""

from __future__ import annotations

from ..core.i18n import tr as _

import json
import os
import re
import signal
import sys
import threading
from pathlib import Path
from typing import Any

from ..core.errors import FlasherError, UnsafeDeviceError
from ..devices.sysfs import identity_from_sysfs, validate_sysname
from ..devices.udisks import UdisksClient
from ..images.detector import inspect_image
from ..utils.logging import get_logger
from .engine import FlashController
from .targets import BlockDeviceTarget, assert_safe_target

log = get_logger("helper")

SYSTEM_MOUNTS = ("/", "/boot", "/boot/efi", "/usr", "/var", "/etc", "/home")


def emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def validate_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("type") != "start":
        raise FlasherError(_("Pedido inválido enviado ao helper."))
    request = payload.get("request")
    if not isinstance(request, dict):
        raise FlasherError(_("Pedido de gravação ausente."))

    image_path = request.get("image_path")
    if not isinstance(image_path, str) or not image_path.startswith("/"):
        raise FlasherError(_("Caminho de imagem inválido."))
    sysname = request.get("target_sysname")
    if not isinstance(sysname, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", sysname):
        raise FlasherError(_("Nome de dispositivo inválido."))
    fingerprint = request.get("expected_fingerprint")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise FlasherError(_("Identidade esperada inválida."))
    chunk_size = request.get("chunk_size", 1024 * 1024)
    if not isinstance(chunk_size, int) or not (64 * 1024 <= chunk_size <= 16 * 1024 * 1024):
        raise FlasherError(_("Tamanho de bloco inválido."))
    verify = request.get("verify", True)
    if not isinstance(verify, bool):
        raise FlasherError(_("Opção de verificação inválida."))
    return {
        "image_path": image_path,
        "target_sysname": validate_sysname(sysname),
        "expected_fingerprint": fingerprint,
        "chunk_size": chunk_size,
        "verify": verify,
    }


def _mounted_system_partitions(sysname: str) -> list[str]:
    """Retorna pontos de montagem críticos pertencentes ao dispositivo."""
    found: list[str] = []
    prefix = f"/dev/{sysname}"
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return found
    for line in lines:
        fields = line.split()
        if len(fields) < 5:
            continue
        mountpoint = fields[4]
        source = ""
        for field in fields:
            if field.startswith("/dev/"):
                source = field
                break
        if source == prefix or source.startswith(prefix + "p") or source.startswith(prefix + "-part"):
            if mountpoint in SYSTEM_MOUNTS:
                found.append(mountpoint)
    return found


def _unmount_target_partitions(sysname: str) -> tuple[bool, str]:
    client = UdisksClient()
    if not client.connect():
        return False, "UDisks2 indisponível."
    mapping = client.partition_paths()
    failures: list[str] = []
    for path in mapping.get(sysname, []):
        ok, error = client.unmount(path)
        if not ok:
            failures.append(error)
    if failures:
        return False, "; ".join(failures)
    return True, ""


def _cancel_watcher(cancel: threading.Event) -> None:
    try:
        for line in sys.stdin:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("type") == "cancel":
                cancel.set()
                return
    except (OSError, ValueError):
        pass


def run_helper() -> int:
    cancel = threading.Event()

    def on_signal(_signum, _frame):  # pragma: no cover - sinal do sistema
        cancel.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, on_signal)
        except (ValueError, OSError):
            pass

    try:
        line = sys.stdin.readline()
        if not line:
            raise FlasherError(_("Helper iniciado sem pedido."))
        request = validate_request(json.loads(line))
    except (ValueError, FlasherError) as exc:
        emit({"type": "error", "message": str(exc)})
        return 2

    threading.Thread(target=_cancel_watcher, args=(cancel,), daemon=True).start()

    try:
        image = inspect_image(Path(request["image_path"]))
        identity = identity_from_sysfs(request["target_sysname"])
        assert_safe_target(identity, request["expected_fingerprint"])

        critical = _mounted_system_partitions(identity.sysname)
        if critical:
            raise UnsafeDeviceError(
                "O dispositivo possui partições do sistema montadas: " + ", ".join(critical)
            )

        unmounted, error = _unmount_target_partitions(identity.sysname)
        if not unmounted:
            raise UnsafeDeviceError("Não foi possível desmontar o dispositivo: " + error)

        target = BlockDeviceTarget(identity)
        controller = FlashController(
            image,
            target,
            verify=request["verify"],
            chunk_size=request["chunk_size"],
            cancel=cancel,
        )

        def progress(progress_event) -> None:
            emit(
                {
                    "type": "progress",
                    "stage": progress_event.stage,
                    "done": progress_event.done,
                    "total": progress_event.total,
                    "speed": progress_event.speed,
                    "eta": progress_event.eta,
                    "message": progress_event.message,
                }
            )

        result = controller.run(progress)

        emit(
            {
                "type": "result",
                "success": bool(result.success),
                "result": {
                    "success": bool(result.success),
                    "verified": bool(result.verified),
                    "cancelled": bool(result.cancelled),
                    "bytes_written": result.bytes_written,
                    "duration": result.duration,
                    "sha256": result.sha256,
                    "error": result.error,
                    "image": image.to_dict(),
                    "device": identity.to_dict(),
                },
            }
        )
        return 0 if result.success else 1
    except FlasherError as exc:
        log.error("Helper abortou: %s", exc)
        emit({"type": "error", "message": str(exc)})
        return 3
    except Exception as exc:  # pragma: no cover - último resource de defesa
        log.exception("Falha inesperada no helper")
        emit({"type": "error", "message": f"Falha inesperada no helper: {exc}"})
        return 4
