#!/usr/bin/env bash
# Gera linux-iso-flasher-x86_64.AppImage a partir da árvore do repositório.
#
# Dependências:
#   - python3 >= 3.11 com pip e setuptools/wheel;
#   - appimagetool (via variável APPIMAGE_TOOL ou no PATH);
#   - opcional: linuxdeploy, caso se queira gerar o AppDir com plugins extras.
#
# Uso:
#   APPIMAGE_TOOL=/caminho/appimagetool ./packaging/appimage/build-appimage.sh
#
# Atenção: o AppImage roda fora do sandbox do Flatpak, mas o pkexec continua
# exigindo um helper e uma política Polkit instalados no HOST. Veja docs/INSTALL.md.
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
APPDIR="$(mktemp -d "${TMPDIR:-/tmp}/linux-iso-flasher-appdir.XXXXXX")"
OUTPUT="${OUTPUT:-$PROJECT_ROOT/linux-iso-flasher-x86_64.AppImage}"
ARCH="${ARCH:-x86_64}"
SITE_DIR="$APPDIR/usr/lib/python3/site-packages"
PYTHON_BIN="${PYTHON:-python3}"

cleanup() {
  rm -rf "$APPDIR"
}
trap cleanup EXIT

tool="${APPIMAGE_TOOL:-}"
if [[ -z "$tool" ]]; then
  tool="$(command -v appimagetool || true)"
fi
if [[ -z "$tool" || ! -x "$tool" ]]; then
  echo "Erro: appimagetool não encontrado. Defina APPIMAGE_TOOL ou coloque-o no PATH." >&2
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Erro: interpretador Python '$PYTHON_BIN' não encontrado." >&2
  exit 1
fi

echo "==> Instalando o projeto em $SITE_DIR"
"$PYTHON_BIN" -m pip install --no-deps --ignore-installed --no-build-isolation \
  --target "$SITE_DIR" "$PROJECT_ROOT"

echo "==> Montando o AppDir"
install -Dm0644 "$PROJECT_ROOT/packaging/desktop/linux-iso-flasher.desktop" \
  "$APPDIR/usr/share/applications/linux-iso-flasher.desktop"
install -Dm0644 "$PROJECT_ROOT/packaging/desktop/linux-iso-flasher.desktop" \
  "$APPDIR/linux-iso-flasher.desktop"
install -Dm0644 "$PROJECT_ROOT/assets/icons/io.github.linuxisoflasher.svg" \
  "$APPDIR/usr/share/icons/hicolor/scalable/apps/io.github.linuxisoflasher.svg"
install -Dm0644 "$PROJECT_ROOT/assets/icons/io.github.linuxisoflasher.svg" \
  "$APPDIR/io.github.linuxisoflasher.svg"
install -Dm0755 "$PROJECT_ROOT/packaging/helper/helper" \
  "$APPDIR/usr/libexec/linux-iso-flasher/helper"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
set -e
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="$HERE/usr/lib/python3/site-packages${PYTHONPATH:+:$PYTHONPATH}"
export LD_LIBRARY_PATH="$HERE/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# O helper/host e a política Polkit devem existir no sistema anfitrião;
# não apontamos LIF_HELPER para dentro do AppImage (o caminho de montagem muda).
exec "${PYTHON:-python3}" -m linux_iso_flasher.main "$@"
APPRUN
chmod 0755 "$APPDIR/AppRun"

echo "==> Gerando $OUTPUT"
rm -f "$OUTPUT"
ARCH="$ARCH" "$tool" "$APPDIR" "$OUTPUT"
echo "Pronto: $OUTPUT"
