#!/usr/bin/env python3
"""Ponto de entrada do helper privilegiado (executado por pkexec).

Em uma instalação pelo pacote, o arquivo em
``/usr/libexec/linux-iso-flasher/helper`` é um wrapper que importa este módulo.
Em execuções a partir do repositório, este arquivo encontra o pacote ``src``
automaticamente.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
for candidate in (
    _HERE.parent.parent.parent,  # src/linux_iso_flasher/flashing -> src
    Path("/usr/lib/linux-iso-flasher"),
):
    if (candidate / "linux_iso_flasher" / "__init__.py").is_file():
        sys.path.insert(0, str(candidate))
        break

# pkexec limpa variáveis de ambiente; garantimos UTF-8 no protocolo.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from linux_iso_flasher.flashing.helper import run_helper  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_helper())
