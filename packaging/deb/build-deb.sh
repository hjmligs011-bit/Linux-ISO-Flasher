#!/usr/bin/env bash
# Gera um .deb binário sem depender de debhelper/dh-python.
# Funciona em qualquer distro que tenha dpkg-deb (inclusive Artix/Arch).
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
VERSION="0.1.0"
DEB_REVISION="1"
ARCH="all"
PACKAGE="linux-iso-flasher"
MODULE_DIR="linux_iso_flasher"
FULL_VERSION="${VERSION}-${DEB_REVISION}"
OUT_DIR="${OUT_DIR:-$PROJECT_ROOT/dist}"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/linux-iso-flasher-deb.XXXXXX")"
DEST="$WORK_DIR/${PACKAGE}_${FULL_VERSION}_${ARCH}"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "Erro: dpkg-deb não encontrado." >&2
  exit 1
fi

mkdir -p "$DEST/DEBIAN"
mkdir -p "$DEST/usr/bin"
mkdir -p "$DEST/usr/lib/python3/dist-packages/$MODULE_DIR"
mkdir -p "$DEST/usr/libexec/$PACKAGE"
mkdir -p "$DEST/usr/share/applications"
mkdir -p "$DEST/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$DEST/usr/share/polkit-1/actions"
mkdir -p "$DEST/usr/share/doc/$PACKAGE"

echo "==> Copiando o módulo Python"
cp -a "$PROJECT_ROOT/src/$MODULE_DIR/." \
  "$DEST/usr/lib/python3/dist-packages/$MODULE_DIR/"
find "$DEST/usr/lib/python3/dist-packages/$MODULE_DIR" \
  -type d -name __pycache__ -prune -exec rm -rf {} +

echo "==> Instalando helper, política e dados de desktop"
install -Dm0755 "$PROJECT_ROOT/packaging/helper/helper" \
  "$DEST/usr/libexec/$PACKAGE/helper"
install -Dm0644 "$PROJECT_ROOT/src/linux_iso_flasher/flashing/helper_entry.py" \
  "$DEST/usr/libexec/$PACKAGE/helper_entry.py"
install -Dm0644 "$PROJECT_ROOT/packaging/desktop/linux-iso-flasher.desktop" \
  "$DEST/usr/share/applications/linux-iso-flasher.desktop"
install -Dm0644 "$PROJECT_ROOT/assets/icons/io.github.linuxisoflasher.svg" \
  "$DEST/usr/share/icons/hicolor/scalable/apps/io.github.linuxisoflasher.svg"
install -Dm0644 "$PROJECT_ROOT/packaging/polkit/org.linuxisoflasher.pkexec.policy" \
  "$DEST/usr/share/polkit-1/actions/org.linuxisoflasher.pkexec.policy"

for lang in en pt_BR; do
  install -Dm0644 \
    "$PROJECT_ROOT/src/linux_iso_flasher/locale/$lang/LC_MESSAGES/linux-iso-flasher.mo" \
    "$DEST/usr/share/locale/$lang/LC_MESSAGES/linux-iso-flasher.mo"
done

cat > "$DEST/usr/bin/linux-iso-flasher" <<'EOF'
#!/usr/bin/python3
from linux_iso_flasher.main import main

raise SystemExit(main())
EOF
chmod 0755 "$DEST/usr/bin/linux-iso-flasher"

echo "==> Instalando documentação"
install -Dm0644 "$PROJECT_ROOT/packaging/deb/copyright" \
  "$DEST/usr/share/doc/$PACKAGE/copyright"
install -Dm0644 "$PROJECT_ROOT/LICENSE" \
  "$DEST/usr/share/doc/$PACKAGE/LICENSE"
install -Dm0644 "$PROJECT_ROOT/README.md" \
  "$DEST/usr/share/doc/$PACKAGE/README.md"
for doc in "$PROJECT_ROOT"/docs/*.md "$PROJECT_ROOT/CONTRIBUTING.md"; do
  install -Dm0644 "$doc" "$DEST/usr/share/doc/$PACKAGE/$(basename "$doc")"
done
cp "$PROJECT_ROOT/packaging/deb/changelog" \
  "$DEST/usr/share/doc/$PACKAGE/changelog.Debian"
gzip -n -9 "$DEST/usr/share/doc/$PACKAGE/changelog.Debian"

INSTALLED_SIZE="$(du -sk "$DEST" | awk '{print $1}')"
cat > "$DEST/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $FULL_VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: Linux ISO Flasher contributors <linux-iso-flasher@example.invalid>
Installed-Size: $INSTALLED_SIZE
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1,
 udisks2, policykit-1, zstd, hicolor-icon-theme
Description: Gravador de imagens ISO/IMG para dispositivos removíveis
 Interface GTK4/libadwaita para gravar imagens em mídia removível via
 UDisks2, com verificação byte a byte e autorização Polkit. A GUI nunca
 executa como root; a gravação acontece em um helper privilegiado.
 .
 Write ISO/IMG images to removable devices with a GTK4/libadwaita
 interface. Enumeration and unmounting use UDisks2; writing is performed
 by a Polkit-authorized root helper with byte-for-byte verification.
EOF

echo "==> Gerando $OUT_DIR/${PACKAGE}_${FULL_VERSION}_${ARCH}.deb"
mkdir -p "$OUT_DIR"
dpkg-deb --root-owner-group --build "$DEST" \
  "$OUT_DIR/${PACKAGE}_${FULL_VERSION}_${ARCH}.deb"
echo "Pacote pronto: $OUT_DIR/${PACKAGE}_${FULL_VERSION}_${ARCH}.deb"
