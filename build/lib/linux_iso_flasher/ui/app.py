"""Aplicação Adwaita: ciclo de vida, ações globais e estilo."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gio, Gtk, GLib  # noqa: E402

from .. import APP_ID  # noqa: E402
from ..core.i18n import set_language  # noqa: E402
from ..utils.logging import get_logger  # noqa: E402

log = get_logger("ui")


class FlasherApplication(Adw.Application):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.config = config
        self._active_window: Adw.ApplicationWindow | None = None
        self._install_actions()

    def _install_actions(self) -> None:
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Ctrl>Q"])

    def do_startup(self) -> None:  # noqa: N802
        Adw.Application.do_startup(self)
        self._load_css()
        self._apply_theme(self.config.get("theme", "dark"))

    def do_activate(self) -> None:  # noqa: N802
        from .window import FlasherWindow

        window = FlasherWindow(application=self, config=self.config)
        self.add_window(window)
        self._active_window = window
        window.present()

    def _load_css(self) -> None:
        css_path = Path(__file__).with_name("theme.css")
        if not css_path.is_file():
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _apply_theme(self, theme: str) -> None:
        manager = Adw.StyleManager.get_default()
        values = {
            "dark": Adw.ColorScheme.FORCE_DARK,
            "light": Adw.ColorScheme.FORCE_LIGHT,
            "system": Adw.ColorScheme.PREFER_DARK,
        }
        manager.set_color_scheme(values.get(theme, values["dark"]))

    def set_theme(self, theme: str) -> None:
        self.config["theme"] = theme
        self._apply_theme(theme)

    def set_language(self, language: str) -> None:
        """Aplica o idioma recriando a janela (sem perder o processo)."""
        from ..core.config import save_config
        from ..core.i18n import current_language

        if current_language() == language:
            return
        self.config["language"] = language
        save_config(self.config)
        set_language(language)
        if self._active_window is not None:
            self._active_window.close()
            self._active_window = None
        self.activate()

    def relaunch(self) -> None:
        """Reinicia o processo com o Python e argumentos atuais."""
        import os

        os.execv(sys.executable, [sys.executable, "-m", "linux_iso_flasher.main", *sys.argv[1:]])
