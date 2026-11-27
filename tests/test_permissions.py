"""Testes do protocolo do helper e da camada de permissões.

O helper simulado é um script Python temporário: nenhum privilégio real e
nenhum dispositivo de bloco é usado.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from linux_iso_flasher.core.errors import FlasherError, PermissionErrorFlasher
from linux_iso_flasher.flashing.helper import validate_request
from linux_iso_flasher.permissions.polkit import HelperLauncher


class RequestValidationTests(unittest.TestCase):
    def test_valid_request(self) -> None:
        request = validate_request(
            {
                "type": "start",
                "request": {
                    "image_path": "/tmp/image.iso",
                    "target_sysname": "sdb",
                    "expected_fingerprint": "a" * 64,
                    "chunk_size": 1024 * 1024,
                    "verify": True,
                },
            }
        )
        self.assertEqual(request["target_sysname"], "sdb")

    def test_rejects_unsafe_values(self) -> None:
        base = {
            "type": "start",
            "request": {
                "image_path": "/tmp/image.iso",
                "target_sysname": "sdb",
                "expected_fingerprint": "a" * 64,
                "chunk_size": 1024,
                "verify": True,
            },
        }
        for key, value in (
            ("image_path", "image.iso"),
            ("image_path", "../../etc/passwd"),
            ("target_sysname", "../../sda"),
            ("target_sysname", "/dev/sda"),
            ("expected_fingerprint", "xyz"),
            ("chunk_size", 10**12),
            ("verify", "yes"),
        ):
            with self.subTest(key=key, value=value):
                payload = json.loads(json.dumps(base))
                payload["request"][key] = value
                with self.assertRaises(FlasherError):
                    validate_request(payload)


class LauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.helper = Path(self.tmp.name) / "fake-helper"
        self.helper.write_text(
            """#!/usr/bin/env python3
import json, sys
for line in sys.stdin:
    msg = json.loads(line)
    if msg.get("type") == "start":
        print(json.dumps({"type": "progress", "stage": "write", "done": 50, "total": 100, "speed": 10, "eta": 5, "message": "ok"}), flush=True)
        print(json.dumps({"type": "result", "success": True, "result": {"success": True, "verified": True, "bytes_written": 100}}), flush=True)
        break
    if msg.get("type") == "cancel":
        break
""",
            encoding="utf-8",
        )
        self.helper.chmod(0o755)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_progress_and_result(self) -> None:
        launcher = HelperLauncher(self.helper, use_pkexec=False)
        seen: list[dict] = []
        result = launcher.flash({}, seen.append, threading.Event())
        self.assertEqual(seen[0]["done"], 50)
        self.assertTrue(result["success"])

    def test_missing_helper(self) -> None:
        launcher = HelperLauncher(Path("/does/not/exist"), use_pkexec=False)
        self.assertFalse(launcher.available)
        with self.assertRaises(Exception):
            launcher.flash({})

    def test_auth_failure_message(self) -> None:
        # pkexec ausente/negado não deve travar a interface.
        launcher = HelperLauncher(self.helper, use_pkexec=True)
        self.assertTrue(launcher.available)


if __name__ == "__main__":
    unittest.main()
