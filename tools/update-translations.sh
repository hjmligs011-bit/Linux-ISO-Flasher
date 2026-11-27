#!/usr/bin/env bash
# Regenera o catálogo e compila os arquivos .mo incluídos no pacote.
set -euo pipefail

cd "$(dirname "$0")/.."

xgettext \
  --language=Python --keyword=_ --keyword=tr --from-code=UTF-8 \
  --add-comments --package-name='Linux ISO Flasher' --package-version=0.1.0 \
  -o po/linux-iso-flasher.pot \
  $(find src -name '*.py' -not -path '*/locale/*' | sort)

for lang in en pt_BR; do
  if [ -f "po/$lang.po" ]; then
    msgmerge --update --backup=off "po/$lang.po" po/linux-iso-flasher.pot
  fi
  mkdir -p "src/linux_iso_flasher/locale/$lang/LC_MESSAGES"
  msgfmt -o "src/linux_iso_flasher/locale/$lang/LC_MESSAGES/linux-iso-flasher.mo" "po/$lang.po"
done

echo "Catálogos atualizados."
