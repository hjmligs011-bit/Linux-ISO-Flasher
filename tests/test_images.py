"""Testes de detecção, leitura e validação de imagens."""

from __future__ import annotations

import gzip
import lzma
import tempfile
import unittest
from pathlib import Path

from linux_iso_flasher.core.errors import ImageError, UnsupportedFormatError
from linux_iso_flasher.images.detector import inspect_image
from linux_iso_flasher.images.reader import open_image_stream

PAYLOAD = (b"linux-iso-flasher-test-image\n" * 5000) + bytes(range(256)) * 200


class ImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, name: str, data: bytes) -> Path:
        path = self.dir / name
        path.write_bytes(data)
        return path

    def _read_all(self, path: Path, info=None) -> bytes:
        info = info or inspect_image(path)
        with open_image_stream(info) as chunks:
            return b"".join(chunks)

    def test_raw_image(self) -> None:
        path = self._write("disk.iso", PAYLOAD)
        info = inspect_image(path)
        self.assertEqual(info.fmt, "iso")
        self.assertIsNone(info.container)
        self.assertEqual(info.size, len(PAYLOAD))
        self.assertEqual(info.uncompressed_size, len(PAYLOAD))
        self.assertEqual(self._read_all(path), PAYLOAD)

    def test_xz_image(self) -> None:
        path = self._write("disk.img.xz", lzma.compress(PAYLOAD))
        info = inspect_image(path)
        self.assertEqual(info.container, "xz")
        self.assertEqual(info.fmt, "img")
        self.assertEqual(info.uncompressed_size, len(PAYLOAD))
        self.assertEqual(self._read_all(path), PAYLOAD)

    def test_gzip_image(self) -> None:
        path = self._write("disk.raw.gz", gzip.compress(PAYLOAD, mtime=0))
        info = inspect_image(path)
        self.assertEqual(info.container, "gz")
        self.assertEqual(info.fmt, "raw")
        self.assertIsNotNone(info.uncompressed_size)
        self.assertEqual(self._read_all(path), PAYLOAD)

    def test_zstd_image(self) -> None:
        try:
            from compression import zstd
        except ImportError:
            self.skipTest("compression.zstd indisponível neste Python")
        path = self._write("disk.bin.zst", zstd.compress(PAYLOAD))
        info = inspect_image(path)
        self.assertEqual(info.container, "zst")
        self.assertEqual(info.fmt, "bin")
        self.assertEqual(self._read_all(path), PAYLOAD)

    def test_unsupported_and_empty(self) -> None:
        with self.assertRaises(UnsupportedFormatError):
            inspect_image(self._write("virus.exe", PAYLOAD))
        with self.assertRaises(ImageError):
            inspect_image(self._write("empty.iso", b""))

    def test_corrupt_compressed_image_is_rejected(self) -> None:
        path = self._write("broken.iso.xz", lzma.compress(PAYLOAD)[:-3] + b"\x00\x00\x00")
        with self.assertRaises(ImageError):
            inspect_image(path)

    def test_missing_file(self) -> None:
        with self.assertRaises(ImageError):
            inspect_image(self.dir / "missing.iso")


if __name__ == "__main__":
    unittest.main()
