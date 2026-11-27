"""Testes do histórico local."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from linux_iso_flasher.core.models import DeviceIdentity, FlashResult, ImageInfo
from linux_iso_flasher.history.store import HistoryStore


def result(name: str, success: bool, verified: bool) -> FlashResult:
    image = ImageInfo(
        path=Path("/tmp") / name,
        size=1024,
        fmt="iso",
        container=None,
        uncompressed_size=1024,
    )
    device = DeviceIdentity(
        sysname="sdb",
        syspath="/sys/block/sdb",
        devpath="/dev/sdb",
        size=4096,
        major=8,
        minor=16,
        vendor="Test",
        model="USB",
        serial="ABC123",
        transport="usb",
        removable=True,
    )
    return FlashResult(
        success=success,
        image=image,
        device=device,
        bytes_written=1024,
        duration=2.5,
        sha256="a" * 64,
        verified=verified,
        error=None if success else "falha",
        timestamp=datetime(2026, 1, 2, 3, 4, 5),
    )


class HistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = HistoryStore(Path(self.tmp.name) / "history.json", limit=2)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_load_and_clear(self) -> None:
        self.store.add(result("a.iso", True, True))
        self.store.add(result("b.iso", False, False))
        entries = self.store.load()
        self.assertEqual([e.image_name for e in entries], ["b.iso", "a.iso"])
        self.assertFalse(entries[0].success)
        self.store.clear()
        self.assertEqual(self.store.load(), [])

    def test_limit(self) -> None:
        for i in range(5):
            self.store.add(result(f"image{i}.iso", True, True))
        self.assertEqual(len(self.store.load()), 2)

    def test_corrupt_file_is_ignored(self) -> None:
        self.store.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.store.load(), [])


if __name__ == "__main__":
    unittest.main()
