"""Gerenciador de dispositivos usado pela interface."""

from __future__ import annotations

from typing import Callable

from ..core.models import DeviceInfo
from ..utils.logging import get_logger
from .udisks import UdisksClient

log = get_logger("devices")


class DeviceManager:
    """Fachada estável sobre UDisks2 com notificação de mudanças."""

    def __init__(self, client: UdisksClient | None = None) -> None:
        self.client = client or UdisksClient()
        self.devices: list[DeviceInfo] = []
        self.available: bool = False
        self._listener: Callable[[list[DeviceInfo]], None] | None = None

    def refresh(self) -> list[DeviceInfo]:
        """Atualiza a lista. Retorna True não houve erro de barramento."""
        try:
            self.devices = self.client.enumerate()
            self.available = True
        except Exception as exc:  # UDisks2 pode sair temporariamente
            self.available = False
            log.warning("Falha ao enumerar dispositivos: %s", exc)
        if self._listener is not None:
            self._listener(self.devices)
        return self.devices

    def find(self, sysname: str) -> DeviceInfo | None:
        for device in self.devices:
            if device.identity.sysname == sysname:
                return device
        return None

    def subscribe(self, listener: Callable[[list[DeviceInfo]], None]) -> None:
        self._listener = listener
        self.client.subscribe(self._on_backend_change)

    def _on_backend_change(self) -> None:
        # Executa na thread principal via idle_add do UdisksClient.
        self.refresh()

    def close(self) -> None:
        self.client.unsubscribe()
