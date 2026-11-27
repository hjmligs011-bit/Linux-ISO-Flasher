"""Ponto de entrada da interface gráfica.

A GUI roda sempre como usuário comum; privilégios são solicitados apenas no
momento da gravação, pelo helper via pkexec/Polkit.
"""

from __future__ import annotations

import sys

from .core.config import load_config
from .core.i18n import install_builtins, setup
from .utils.logging import get_logger, setup_logging


def main() -> int:
    config = load_config()
    setup_logging()
    language = setup(config.get("language"))
    install_builtins()
    log = get_logger("main")
    log.info("Iniciando Linux ISO Flasher (idioma=%s)", language)

    from .ui.app import FlasherApplication

    app = FlasherApplication(config)
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
