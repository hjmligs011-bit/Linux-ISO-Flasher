"""Testes do verificador de integridade (arquivos temporários apenas)."""

from __future__ import annotations

import hashlib
import tempfile
import threading
import unittest
from pathlib import Path

from linux_iso_flasher.core.errors import CancelledError, VerificationError
from linux_iso_flasher.flashing.targets import FileTarget
from linux_iso_flasher.images.detector import inspect_image
from linux_iso_flasher.verification.verifier import IntegrityVerifier

PAYLOAD = bytes(range(256)) * 600


class VerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _setup(self, written: bytes):
        image_path = self.dir / "data.iso"
        image_path.write_bytes(PAYLOAD)
        target_path = self.dir / "target.bin"
        target_path.write_bytes(written)
        target = FileTarget(target_path)
        target.prepare()
        self.addCleanup(target.close)
        return inspect_image(image_path), target

    def test_matching_data(self) -> None:
        image, target = self._setup(PAYLOAD)
        result = IntegrityVerifier(image, target, chunk_size=8192).run(len(PAYLOAD))
        self.assertTrue(result.verified)
        self.assertEqual(result.bytes_checked, len(PAYLOAD))
        self.assertEqual(result.digest, hashlib.sha256(PAYLOAD).hexdigest())

    def test_mismatch_is_detected(self) -> None:
        corrupted = bytearray(PAYLOAD)
        corrupted[1234] ^= 0xFF
        image, target = self._setup(bytes(corrupted))
        with self.assertRaises(VerificationError):
            IntegrityVerifier(image, target, chunk_size=8192).run(len(PAYLOAD))

    def test_length_mismatch_is_detected(self) -> None:
        image, target = self._setup(PAYLOAD[:-10])
        with self.assertRaises(VerificationError):
            IntegrityVerifier(image, target, chunk_size=8192).run(len(PAYLOAD))

    def test_cancel_during_verification(self) -> None:
        image, target = self._setup(PAYLOAD)
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(CancelledError):
            IntegrityVerifier(image, target, cancel=cancel).run(len(PAYLOAD))


if __name__ == "__main__":
    unittest.main()
