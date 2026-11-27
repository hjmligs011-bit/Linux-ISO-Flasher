"""Testes de sysfs e do parser de objetos UDisks2 (sem dispositivos reais)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from linux_iso_flasher.core.errors import DeviceError  # noqa: E402
from linux_iso_flasher.devices.sysfs import (  # noqa: E402
    identity_from_sysfs,
    validate_sysname,
)
from linux_iso_flasher.devices.udisks import (  # noqa: E402
    BLOCK_IFACE,
    DRIVE_IFACE,
    FS_IFACE,
    PARTITION_IFACE,
    UdisksClient,
)


def ay(value: str) -> GLib.Variant:
    return GLib.Variant("ay", value.encode() + b"\x00")


class SysfsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        block = root / "block" / "sdb"
        (block / "device").mkdir(parents=True)
        (block / "queue").mkdir()
        (block / "size").write_text("204800\n")
        (block / "dev").write_text("8:16\n")
        (block / "removable").write_text("1\n")
        (block / "device" / "vendor").write_text("SanDisk\n")
        (block / "device" / "model").write_text("Ultra Fit\n")
        (block / "device" / "serial").write_text("4C530001234\n")
        (block / "device" / "transport").write_text("usb\n")
        self.root = root

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_identity(self) -> None:
        identity = identity_from_sysfs("sdb", self.root)
        self.assertEqual(identity.size, 204800 * 512)
        self.assertEqual((identity.major, identity.minor), (8, 16))
        self.assertTrue(identity.removable)
        self.assertEqual(identity.transport, "usb")
        self.assertEqual(identity.name, "SanDisk Ultra Fit")
        self.assertEqual(len(identity.fingerprint), 64)

    def test_fingerprint_ignores_device_name(self) -> None:
        first = identity_from_sysfs("sdb", self.root)
        second = identity_from_sysfs("sdb", self.root)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_missing_device(self) -> None:
        with self.assertRaises(Exception):
            identity_from_sysfs("sdz", self.root)

    def test_path_traversal_blocked(self) -> None:
        with self.assertRaises(DeviceError):
            validate_sysname("../../etc")
        with self.assertRaises(DeviceError):
            validate_sysname("/dev/sda")


class UdisksParserTests(unittest.TestCase):
    def test_partitions_and_mounts(self) -> None:
        parent = "/org/freedesktop/UDisks2/block_devices/sdb"
        props_partition = {
            "Number": GLib.Variant("u", 1),
            "Name": GLib.Variant("s", "ISO"),
            "Size": GLib.Variant("t", 512 * 1024),
        }
        props_fs = {
            "IdLabel": GLib.Variant("s", "LIF_TEST"),
            "IdType": GLib.Variant("s", "vfat"),
            "MountPoints": GLib.Variant("aay", [b"/media/user/LIF_TEST\x00"]),
        }
        objects = {
            parent: {BLOCK_IFACE: {"Device": ay("/dev/sdb")}},
            parent + "/sdb1": {
                PARTITION_IFACE: props_partition,
                FS_IFACE: props_fs,
            },
        }
        partitions = UdisksClient._partitions(objects, parent)
        self.assertEqual(len(partitions), 1)
        self.assertEqual(partitions[0].label, "LIF_TEST")
        self.assertEqual(partitions[0].filesystem, "vfat")
        self.assertEqual(partitions[0].mount_points, ("/media/user/LIF_TEST",))

    def test_dbus_value_conversion(self) -> None:
        from linux_iso_flasher.devices.udisks import _number, _text

        self.assertEqual(_text(ay("usb\x00")), "usb")
        self.assertEqual(_number(GLib.Variant("t", 4096)), 4096)


if __name__ == "__main__":
    unittest.main()
