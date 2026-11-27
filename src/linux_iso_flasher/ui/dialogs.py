"""Diálogos reutilizáveis: preferências e sobre."""

from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import APP_ID, __version__  # noqa: E402


class PreferencesDialog(Adw.PreferencesDialog):
    """Tema e idioma, persistidos imediatamente."""

    def __init__(self, config: dict[str, Any], on_theme, on_language) -> None:
        super().__init__(title=_("Preferências"))
        self.config = config
        self._on_theme = on_theme
        self._on_language = on_language

        page = Adw.PreferencesPage()

        appearance = Adw.PreferencesGroup(title=_("Aparência"))
        theme = Adw.ComboRow(
            title=_("Tema"),
            subtitle=_("Escolha como o aplicativo deve aparecer."),
            model=Gtk.StringList.new([_("Escuro"), _("Claro"), _("Automático")]),
        )
        theme.set_selected(["dark", "light", "system"].index(config.get("theme", "dark")))
        theme.connect("notify::selected", self._theme_changed)
        appearance.add(theme)
        page.add(appearance)

        language = Adw.PreferencesGroup(title=_("Idioma"))
        lang_row = Adw.ComboRow(
            title=_("Idioma da interface"),
            subtitle=_("Português brasileiro é o padrão."),
            model=Gtk.StringList.new(["Português (Brasil)", "English"]),
        )
        lang_row.set_selected(0 if config.get("language") == "pt_BR" else 1)
        lang_row.connect("notify::selected", self._language_changed)
        language.add(lang_row)
        page.add(language)

        verification = Adw.PreferencesGroup(
            title=_("Verificação"),
            description=_("A verificação SHA-256 após a gravação é sempre executada."),
        )
        switch = Adw.SwitchRow(
            title=_("Verificar dados gravados"),
            subtitle=_("Compara a imagem com o dispositivo byte a byte."),
            active=True,
            sensitive=False,
        )
        verification.add(switch)
        page.add(verification)

        self.add(page)

    def _theme_changed(self, row: Adw.ComboRow, _pspec) -> None:
        value = ["dark", "light", "system"][row.get_selected()]
        self._on_theme(value)

    def _language_changed(self, row: Adw.ComboRow, _pspec) -> None:
        value = ["pt_BR", "en"][row.get_selected()]
        self._on_language(value)


def about_dialog() -> Adw.AboutDialog:
    dialog = Adw.AboutDialog()
    dialog.set_application_name(_("Linux ISO Flasher"))
    dialog.set_version(__version__)
    dialog.set_developer_name("Linux ISO Flasher contributors")
    dialog.set_comments(
        _("Grave imagens de sistemas operacionais em USB e cartões SD com segurança.")
    )
    dialog.set_license_type(Adw.License.GPL_3_0_OR_LATER)
    dialog.set_application_icon(APP_ID)
    return dialog
