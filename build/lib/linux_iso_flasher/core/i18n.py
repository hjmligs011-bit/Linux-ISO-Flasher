"""Internacionalização (gettext).

As strings do código-fonte estão em português brasileiro (idioma padrão).
O catálogo ``en`` fornece a tradução alternativa para inglês.
"""

from __future__ import annotations

import gettext
import locale
import os
from pathlib import Path

DOMAIN = "linux-iso-flasher"
_SUPPORTED = ("pt_BR", "en")

_current = "pt_BR"
_translation: gettext.NullTranslations = gettext.NullTranslations()


def locale_dir() -> Path:
    """Diretório com os catálogos compilados (.mo)."""
    packaged = Path(__file__).resolve().parent.parent / "locale"
    if (packaged / "en" / "LC_MESSAGES" / f"{DOMAIN}.mo").is_file():
        return packaged
    # Instalação pelo setuptools: share/locale/<lang>/LC_MESSAGES
    installed = Path(__file__).resolve().parents[3] / "share" / "locale"
    if installed.is_dir():
        return installed
    return packaged


def _detect_requested_language() -> str:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if not value:
            continue
        for part in value.split(":"):
            base = part.split(".")[0].replace("-", "_")
            if base in _SUPPORTED:
                return base
            if base == "pt" or base.startswith("pt_"):
                return "pt_BR"
            if base == "en" or base.startswith("en_"):
                return "en"
    return "pt_BR"


def setup(preferred: str | None = None) -> str:
    """Instala o catálogo e retorna o idioma efetivo."""
    global _current, _translation, _
    requested = preferred if preferred in _SUPPORTED else _detect_requested_language()
    try:
        _translation = gettext.translation(
            DOMAIN, localedir=locale_dir(), languages=[requested], fallback=True
        )
    except OSError:
        _translation = gettext.NullTranslations()
    _current = requested if isinstance(_translation, gettext.GNUTranslations) else "pt_BR"
    _ = _translation.gettext
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass
    return _current


def set_language(language: str) -> str:
    """Troca o catálogo em tempo de execução (a janela deve ser recriada)."""
    return setup(language)


def current_language() -> str:
    return _current


def tr(message: str) -> str:
    """Traduz uma string (API usada por módulos não-GUI)."""
    return _translation.gettext(message)


def install_builtins() -> None:
    """Exponha ``_`` nos builtins para as strings da interface."""
    import builtins

    builtins._ = tr  # type: ignore[attr-defined]


_ = tr
