"""Testes de gravação e verificação com arquivos temporários.

Nenhum dispositivo de bloco real é utilizado: FileTarget simula apenas a
interface de escrita/leitura por offsets.
"""

from __future__ import annotations

import gzip
import hashlib
import lzma
import os
import tempfile
import threading
import unittest
from pathlib import Path

from linux_iso_flasher.core.errors import ImageError, ImageTooLargeError
from linux_iso_flasher.core.models import FlashProgress
from linux_iso_flasher.flashing.engine import FlashController
from linux_iso_flasher.flashing.targets import FileTarget
from linux_iso_flasher.images.detector import inspect_image

PAYLOAD = b"".join(bytes([i % 251]) * 997 for i in range(80))  # ~80 KiB


class FlashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _setup(self, image_bytes: bytes, name: str, capacity: int | None = None):
        image_path = self.dir / name
        image_path.write_bytes(image_bytes)
        info = inspect_image(image_path)
        target_path = self.dir / "target.img"
        with target_path.open("wb") as handle:
            handle.truncate(capacity or max(len(image_bytes) * 4, 256 * 1024))
        return info, target_path

    def test_write_and_verify(self) -> None:
        info, target_path = self._setup(PAYLOAD, "system.iso")
        events: list[FlashProgress] = []
        result = FlashController(info, FileTarget(target_path), chunk_size=8192).run(
            events.append
        )
        self.assertTrue(result.success)
        self.assertTrue(result.verified)
        self.assertEqual(result.bytes_written, len(PAYLOAD))
        self.assertEqual(result.sha256, hashlib.sha256(PAYLOAD).hexdigest())
        self.assertEqual(target_path.read_bytes()[: len(PAYLOAD)], PAYLOAD)
        self.assertTrue(any(e.stage == "write" for e in events))
        self.assertTrue(any(e.stage == "verify" for e in events))
        self.assertTrue(all(0 <= e.percent <= 100 for e in events))

    def test_compressed_image(self) -> None:
        for name, data in (
            ("system.iso.xz", lzma.compress(PAYLOAD)),
            ("system.img.gz", gzip.compress(PAYLOAD)),
        ):
            with self.subTest(name=name):
                info, target_path = self._setup(data, name)
                result = FlashController(info, FileTarget(target_path), chunk_size=8192).run()
                self.assertTrue(result.success, result.error)
                self.assertEqual(target_path.read_bytes()[: len(PAYLOAD)], PAYLOAD)

    def test_capacity_check(self) -> None:
        info, target_path = self._setup(PAYLOAD, "system.iso", capacity=1024)
        result = FlashController(info, FileTarget(target_path)).run()
        self.assertFalse(result.success)
        self.assertIsInstance(result.error, str)

    def test_verification_detects_modified_target(self) -> None:
        info, target_path = self._setup(PAYLOAD, "system.iso")

        class CorruptingTarget(FileTarget):
            def write(self, offset: int, data: bytes) -> None:
                corrupted = bytearray(data)
                corrupted[0] ^= 0xFF
                super().write(offset, bytes(corrupted))

        result = FlashController(
            info, CorruptingTarget(target_path), chunk_size=8192
        ).run()
        self.assertFalse(result.success)
        self.assertFalse(result.verified)
        self.assertIn("diverg", (result.error or "").lower())

    def test_cancel_before_start(self) -> None:
        info, target_path = self._setup(PAYLOAD, "system.iso")
        cancel = threading.Event()
        cancel.set()
        result = FlashController(info, FileTarget(target_path), cancel=cancel).run()
        self.assertFalse(result.success)
        self.assertTrue(result.cancelled)

    def test_cancel_during_write(self) -> None:
        info, target_path = self._setup(PAYLOAD * 8, "system.iso")
        cancel = threading.Event()

        class CancellingTarget(FileTarget):
            def write(self, offset: int, data: bytes) -> None:
                super().write(offset, data)
                cancel.set()

        result = FlashController(
            info, CancellingTarget(target_path), chunk_size=8192, cancel=cancel
        ).run()
        self.assertTrue(result.cancelled)
        self.assertFalse(result.success)
        self.assertFalse(result.verified)

    def test_empty_image_is_rejected(self) -> None:
        info, target_path = self._setup(PAYLOAD, "system.iso")
        empty = self.dir / "empty.iso"
        empty.write_bytes(b"")
        with self.assertRaises(Exception):
            inspect_image(empty)

    def test_target_removed_during_operation(self) -> None:
        info, target_path = self._setup(PAYLOAD, "system.iso")
        cancel = threading.Event()

        class RemovedTarget(FileTarget):
            def write(self, offset: int, data: bytes) -> None:
                super().write(offset, data)
                self.path = Path(str(self.path) + ".removed")
                cancel.set()

        result = FlashController(info, RemovedTarget(target_path), cancel=cancel).run()
        self.assertTrue(result.cancelled)


if __name__ == "__main__":
    unittest.main()
