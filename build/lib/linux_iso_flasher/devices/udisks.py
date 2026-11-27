"""Cliente UDisks2 via Gio.DBus (system bus).

Usa apenas a API oficial do UDisks2: ObjectManager para listar/observar objetos
e Manager.GetBlockDevices para obter dispositivos de bloco. Nenhum comando de
shell é montado a partir de dados do dispositivo.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from ..core.models import DeviceIdentity, DeviceInfo, PartitionInfo  # noqa: E402
from .sysfs import identity_from_sysfs, is_system_device  # noqa: E402

UDISKS_NAME = "org.freedesktop.UDisks2"
UDISKS_PATH = "/org/freedesktop/UDisks2"
OM_IFACE = "org.freedesktop.DBus.ObjectManager"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
BLOCK_IFACE = "org.freedesktop.UDisks2.Block"
DRIVE_IFACE = "org.freedesktop.UDisks2.Drive"
PARTITION_IFACE = "org.freedesktop.UDisks2.Partition"
FS_IFACE = "org.freedesktop.UDisks2.Filesystem"
MANAGER_IFACE = "org.freedesktop.UDisks2.Manager"

PropMap = dict[str, Any]


def _value(raw: Any, default: Any = None) -> Any:
    """Converte um GLib.Variant em valor Python simples."""
    if raw is None:
        return default
    if isinstance(raw, GLib.Variant):
        try:
            kind = raw.get_type_string()
            if kind == "ay":
                return raw.get_bytestring()
            if kind == "aay":
                return [bytes(item) for item in raw.unpack()]
            return raw.unpack()
        except (TypeError, ValueError, AttributeError):
            return default
    return raw


def _text(raw: Any, default: str = "") -> str:
    value = _value(raw)
    if isinstance(value, bytes):
        return value.split(b"\x00", 1)[0].decode("utf-8", "replace")
    if value is None:
        return default
    return str(value)


def _bytes_path(raw: Any) -> str:
    value = _value(raw)
    if isinstance(value, bytes):
        return value.split(b"\x00", 1)[0].decode("utf-8", "replace")
    return str(value or "")


def _number(raw: Any, default: int = 0) -> int:
    value = _value(raw)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class UdisksClient:
    """Acesso ao estado do UDisks2 + desmontagem controlada."""

    def __init__(self) -> None:
        self.connection: Gio.DBusConnection | None = None
        self._subscriptions: list[int] = []
        self._poll_source: int | None = None
        self._callback: Callable[[], None] | None = None

    # ---------------------------------------------------------------- conexão
    def connect(self) -> bool:
        try:
            self.connection = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            return True
        except GLib.Error:
            self.connection = None
            return False

    def _call(
        self, path: str, interface: str, method: str, params: GLib.Variant | None = None,
        timeout_ms: int = 4000,
    ) -> GLib.Variant | None:
        if self.connection is None:
            return None
        if params is None:
            params = GLib.Variant("()", ())
        try:
            return self.connection.call_sync(
                UDISKS_NAME, path, interface, method, params,
                None, Gio.DBusCallFlags.NONE, timeout_ms, None,
            )
        except GLib.Error:
            return None

    # -------------------------------------------------------------- enumeração
    def _managed_objects(self) -> dict[str, dict[str, PropMap]]:
        result = self._call(UDISKS_PATH, OM_IFACE, "GetManagedObjects")
        if result is None:
            return {}
        objects = result.unpack()
        return {
            str(path): {
                str(iface): dict(props) for iface, props in interfaces.items()
            }
            for path, interfaces in objects[0].items()
        }

    def _block_paths(self) -> list[str]:
        options = GLib.Variant("(a{sv})", ({},))
        result = self._call(
            UDISKS_PATH + "/Manager", MANAGER_IFACE, "GetBlockDevices", options
        )
        if result is None:
            return []
        return [str(path) for path in result.unpack()[0]]

    def enumerate(self) -> list[DeviceInfo]:
        """Retorna dispositivos removíveis detectados (nunca discos internos)."""
        objects = self._managed_objects()
        devices: list[DeviceInfo] = []
        for path in self._block_paths():
            interfaces = objects.get(path, {})
            block = interfaces.get(BLOCK_IFACE, {})
            if not block:
                continue

            devpath = _bytes_path(block.get("Device")) or _bytes_path(
                block.get("PreferredDevice")
            )
            if not devpath or "/dev/" not in devpath:
                continue
            sysname = Path(devpath).name
            # partições são filtradas: queremos apenas o dispositivo inteiro
            if any(key.startswith(PARTITION_IFACE) for key in interfaces):
                continue

            drive_path = str(_value(block.get("Drive"), "") or "")
            drive = objects.get(drive_path, {}).get(DRIVE_IFACE, {})
            try:
                identity = identity_from_sysfs(sysname)
            except Exception:
                continue

            removable_dbus = bool(_value(drive.get("Removable"), False))
            connection = _text(drive.get("ConnectionBus"), identity.transport)
            media = _text(drive.get("MediaType")) or _text(drive.get("Media"), identity.media)
            vendor = _text(drive.get("Vendor"), identity.vendor)
            model = _text(drive.get("Model"), identity.model)
            serial = _text(drive.get("Serial"), identity.serial)

            transport = connection or identity.transport
            removable = identity.removable or removable_dbus
            identity = DeviceIdentity(
                sysname=identity.sysname,
                syspath=identity.syspath,
                devpath=identity.devpath,
                size=identity.size or _number(block.get("Size")),
                major=identity.major,
                minor=identity.minor,
                vendor=vendor,
                model=model,
                serial=serial,
                transport=transport,
                removable=removable,
                media=media,
            )

            if not removable:
                # Os discos internos nunca entram na lista da interface.
                continue

            partitions = self._partitions(objects, path)
            available = self._available(partitions)
            devices.append(
                DeviceInfo(
                    identity=identity,
                    partitions=tuple(partitions),
                    available=available,
                    connection=connection or transport,
                    system_disk=is_system_device(identity),
                )
            )
        return sorted(devices, key=lambda d: (d.identity.sysname, d.identity.id))

    @staticmethod
    def _partitions(objects: dict[str, dict[str, PropMap]], parent_path: str) -> list[PartitionInfo]:
        prefix = parent_path.rstrip("/") + "/"
        result: list[PartitionInfo] = []
        for path, interfaces in objects.items():
            if not path.startswith(prefix):
                continue
            props = interfaces.get(PARTITION_IFACE)
            if not props:
                continue
            fs = interfaces.get(FS_IFACE, {})
            mounts = tuple(
                _bytes_path(point)
                for point in (_value(fs.get("MountPoints"), []) or [])
                if _bytes_path(point)
            )
            result.append(
                PartitionInfo(
                    number=_number(props.get("Number")),
                    label=_text(fs.get("IdLabel")) or _text(props.get("Name")),
                    filesystem=_text(fs.get("IdType")),
                    size=_number(props.get("Size"), _number(fs.get("Size"))),
                    mount_points=mounts,
                )
            )
        return sorted(result, key=lambda p: p.number)

    @staticmethod
    def _available(partitions: list[PartitionInfo]) -> int | None:
        values: list[int] = []
        for partition in partitions:
            for mount in partition.mount_points:
                try:
                    stat = os.statvfs(mount)
                except OSError:
                    continue
                values.append(stat.f_bavail * stat.f_frsize)
        return sum(values) if values else None

    # --------------------------------------------------------------- observação
    def subscribe(self, callback: Callable[[], None]) -> None:
        """Observa adições/remoções e mudanças de propriedades do UDisks2."""
        if self.connection is None and not self.connect():
            return
        self._callback = callback
        for member in ("InterfacesAdded", "InterfacesRemoved"):
            try:
                handle = self.connection.signal_subscribe(
                    UDISKS_NAME, OM_IFACE, member, UDISKS_PATH, None,
                    Gio.DBusSignalFlags.NONE,
                    lambda *_args, _cb=callback: self._changed(_cb), None,
                )
                self._subscriptions.append(handle)
            except GLib.Error:
                pass
        try:
            handle = self.connection.signal_subscribe(
                UDISKS_NAME, PROPS_IFACE, "PropertiesChanged", None, None,
                Gio.DBusSignalFlags.NONE,
                lambda *_args, _cb=callback: self._changed(_cb), None,
            )
            self._subscriptions.append(handle)
        except GLib.Error:
            pass
        # Mudanças de montagem/nome nem sempre geram sinal; complementamos com
        # uma pesquisa leve a cada 3 segundos.
        self._poll_source = GLib.timeout_add_seconds(3, self._poll)

    def _changed(self, callback: Callable[[], None]) -> None:
        GLib.idle_add(callback)

    def _poll(self) -> bool:
        if self._callback is not None:
            self._callback()
        return True

    def unsubscribe(self) -> None:
        if self.connection is not None:
            for handle in self._subscriptions:
                try:
                    self.connection.signal_unsubscribe(handle)
                except GLib.Error:
                    pass
        self._subscriptions.clear()
        if self._poll_source is not None:
            GLib.source_remove(self._poll_source)
            self._poll_source = None
        self._callback = None

    # ------------------------------------------------------------- desmontagem
    def unmount(self, object_path: str, force: bool = True) -> tuple[bool, str]:
        """Desmonta uma partição via UDisks2.Filesystem.Unmount."""
        options = GLib.Variant("(a{sv})", ({"force": GLib.Variant("b", force)},))
        result = self._call(
            object_path, FS_IFACE, "Unmount", options, timeout_ms=8000
        )
        if result is None:
            return False, "UDisks2 recusou a desmontagem ou não respondeu."
        return True, ""

    def partition_paths(self) -> dict[str, list[str]]:
        """Mapa sysname -> object paths das partições (para desmontagem)."""
        mapping: dict[str, list[str]] = {}
        objects = self._managed_objects()
        for path in self._block_paths():
            interfaces = objects.get(path, {})
            block = interfaces.get(BLOCK_IFACE, {})
            if not block:
                continue
            sysname = Path(_bytes_path(block.get("Device"))).name
            if not sysname:
                continue
            mapping[sysname] = [
                child
                for child, child_ifaces in objects.items()
                if child.startswith(path.rstrip("/") + "/")
                and PARTITION_IFACE in child_ifaces
                and FS_IFACE in child_ifaces
            ]
        return mapping
