"""Smoke test manual da interface (executa com PYTHONPATH=src).

Usa um helper falso e um dispositivo sintético apenas em memória: nenhum
dispositivo de bloco real é tocado.
"""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib  # noqa: E402

from linux_iso_flasher.core.config import load_config  # noqa: E402
from linux_iso_flasher.core.i18n import install_builtins, setup  # noqa: E402
from linux_iso_flasher.core.models import DeviceIdentity, DeviceInfo  # noqa: E402
from linux_iso_flasher.permissions.polkit import HelperLauncher  # noqa: E402
from linux_iso_flasher.ui.app import FlasherApplication  # noqa: E402

ERRORS: list[str] = []
IMAGE: Path
FAKE_HELPER: Path


class SmokeApp(FlasherApplication):
    def do_activate(self) -> None:  # noqa: N802
        from linux_iso_flasher.ui.window import FlasherWindow

        window = FlasherWindow(application=self, config=self.config)
        self.add_window(window)
        window.present()
        self.window = window
        GLib.timeout_add(300, self._run_checks)

    def _run_checks(self) -> bool:
        window = self.window
        try:
            print("step: set_image", flush=True)
            window._set_image(IMAGE)
            assert window.image_info is not None
            print("step: history/preferences/result", flush=True)
            window._show_history()
            window._show_preferences()
            window._show_result(_fake_result(window))
            window._go_main()

            print("step: flash flow", flush=True)
            identity = DeviceIdentity(
                sysname="sdb", syspath="/sys/block/sdb", devpath="/dev/sdb", size=1 << 20,
                major=8, minor=16, vendor="Fake", model="USB", serial="SMOKE1",
                transport="usb", removable=True,
            )
            window.selected_device = DeviceInfo(identity=identity)
            window.launcher = HelperLauncher(FAKE_HELPER, use_pkexec=False)
            window._begin_flash()
            GLib.timeout_add(150, self._wait_result)
            return False
        except Exception as exc:  # pragma: no cover
            ERRORS.append(f"{type(exc).__name__}: {exc}")
        finally:
            if ERRORS:
                self.quit()
        return False

    def _wait_result(self) -> bool:
        if self.window.stack.get_visible_child_name() == "result":
            print("step: flash result shown", flush=True)
            entries = self.window.history.load()
            if not any(entry.success and entry.verified for entry in entries):
                ERRORS.append("histórico não registrou a gravação verificada")
            if not self.window.result_title.get_label():
                ERRORS.append("título de resultado vazio")
            self.quit()
            return False
        return True


def _fake_result(window) -> dict:
    return {
        "success": False,
        "verified": False,
        "error": "teste",
        "image": window.image_info.to_dict(),
        "device": {
            "sysname": "sdb", "syspath": "/sys/block/sdb", "devpath": "/dev/sdb",
            "size": 1024, "major": 8, "minor": 16, "vendor": "Test", "model": "USB",
            "serial": "1", "transport": "usb", "removable": True, "media": "",
        },
    }


def main() -> int:
    global IMAGE, FAKE_HELPER
    import os

    tmp = tempfile.TemporaryDirectory()
    os.environ["XDG_STATE_HOME"] = tmp.name
    os.environ["XDG_CONFIG_HOME"] = tmp.name
    setup("pt_BR")
    install_builtins()
    config = load_config()
    IMAGE = Path(tmp.name) / "smoke.iso"
    IMAGE.write_bytes(gzip.compress(b"smoke test" * 10000))
    FAKE_HELPER = Path(tmp.name) / "fake-helper"
    FAKE_HELPER.write_text(
        """#!/usr/bin/env python3
import json, sys
for line in sys.stdin:
    msg = json.loads(line)
    if msg.get("type") == "start":
        print(json.dumps({"type": "progress", "stage": "write", "done": 50,
                          "total": 100, "speed": 1048576, "eta": 2,
                          "message": "ok"}), flush=True)
        print(json.dumps({"type": "progress", "stage": "verify", "done": 100,
                          "total": 100, "speed": 1048576, "eta": 0,
                          "message": "ok"}), flush=True)
        print(json.dumps({"type": "result", "success": True, "result": {
            "success": True, "verified": True, "cancelled": False,
            "bytes_written": 100, "duration": 1.5, "sha256": "a" * 64,
            "error": None, "image": msg["request"].get("image", {}),
            "device": {"sysname": "sdb", "syspath": "/sys/block/sdb",
                       "devpath": "/dev/sdb", "size": 1048576, "major": 8,
                       "minor": 16, "vendor": "Fake", "model": "USB",
                       "serial": "SMOKE1", "transport": "usb",
                       "removable": True, "media": ""}}}), flush=True)
        break
""",
        encoding="utf-8",
    )
    FAKE_HELPER.chmod(0o755)
    app = SmokeApp(config)
    app.run([sys.argv[0]])
    tmp.cleanup()
    if ERRORS:
        print("SMOKE FAILED:", *ERRORS, sep="\n")
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
