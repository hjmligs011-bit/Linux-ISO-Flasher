# Instalação — Linux ISO Flasher 0.1.0

Este guia cobre instalação a partir do código-fonte. O projeto usa
`setuptools` com `src/`, entry point `linux-iso-flasher` e Python >= 3.11.

## Dependências comuns

| Dependência | Uso |
| --- | --- |
| GTK 4 + PyGObject (`gi`) | interface |
| libadwaita (typelib `Adw`) | widgets e tema |
| UDisks2 (system bus) | listar/dispositivos e desmontar partições |
| Polkit + `pkexec` | autorizar o helper privilegiado |
| zstd | descomprimir `.zst` quando o Python não traz `compression.zstd` |
| hicolor-icon-theme | ícone no menu |

O processo gráfico **nunca** roda como root. Somente o helper em
`/usr/libexec/linux-iso-flasher/helper` é executado via `pkexec`.

## Arch Linux

```sh
sudo pacman -S gtk4 libadwaita python python-pip python-gobject udisks2 polkit \
               hicolor-icon-theme zstd python-build python-installer
python -m pip install -e .        # ou: python -m build --wheel && python -m pip install dist/*.whl
```

Para o PKGBUILD em `packaging/arch/`: gere o tarball na raiz do repositório e
rode `makepkg -si` dentro do diretório `packaging/arch/` (veja os comentários no
próprio PKGBUILD; `sha256sums` usa `SKIP` apenas para build local).

### Publicar na AUR

O pacote pronto para AUR está em `packaging/aur/` (`PKGBUILD` + `.SRCINFO`).
O `PKGBUILD` aponta para o tarball de release `linux-iso-flasher-0.1.0.tar.gz`
com SHA-256 fixo. Para publicar:

1. Suba `dist/linux-iso-flasher-0.1.0.tar.gz` como asset da release `v0.1.0` no
   GitHub (o URL já está no `source=` do PKGBUILD).
2. Crie o pacote AUR `linux-iso-flasher` e commite `PKGBUILD` e `.SRCINFO`.
3. Usuários instalam com `yay -S linux-iso-flasher` (ou `paru -S ...`).

Para testar localmente antes de publicar:

```sh
cd packaging/aur
cp ../../dist/linux-iso-flasher-0.1.0.tar.gz .
makepkg -si
```

Se o tarball ainda não estiver no GitHub, `makepkg` encontra a cópia local e
valida o `sha256sums` normalmente. Após testar, remova o tarball e o
`.pkg.tar.zst` do diretório AUR antes de commitar.

## Debian / Ubuntu

```sh
sudo apt update
sudo apt install python3 python3-pip python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
                 udisks2 policykit-1 zstd hicolor-icon-theme
python3 -m pip install -e . --break-system-packages
```

Em ambientes com PEP 668, prefira um virtualenv:
`python3 -m venv .venv && . .venv/bin/activate && pip install -e .`.
### Gerando o `.deb`

Instale as dependências de build:

```sh
sudo apt install build-essential debhelper dh-python fakeroot \
                 python3 python3-build python3-pip python3-setuptools python3-wheel tar
```

O esqueleto completo de empacotamento Debian está em `packaging/deb/`:
`control`, `rules`, `changelog`, `copyright` e `source/format`. Ajuste o campo
`Maintainer` em `packaging/deb/control` antes de publicar.

Como o formato de código-fonte é `3.0 (quilt)`, crie primeiro o tarball de
origem e depois um diretório de build com o nome esperado:

```sh
cd /home/miguel
tar --exclude='linux-iso-flasher/build' \
    --exclude='linux-iso-flasher/dist' \
    --exclude='linux-iso-flasher/__pycache__' \
    --exclude='linux-iso-flasher/debian' \
    --transform='s|^linux-iso-flasher|linux-iso-flasher-0.1.0|' \
    -czf linux-iso-flasher_0.1.0.orig.tar.gz linux-iso-flasher

mkdir -p /tmp/lif-deb
cd /tmp/lif-deb
tar -xzf /home/miguel/linux-iso-flasher_0.1.0.orig.tar.gz
cp -a /home/miguel/linux-iso-flasher/packaging/deb \
      /tmp/lif-deb/linux-iso-flasher-0.1.0/debian
cd /tmp/lif-deb/linux-iso-flasher-0.1.0
dpkg-buildpackage -us -uc -b
```

O pacote pronto fica em `/tmp/lif-deb/linux-iso-flasher_0.1.0-1_all.deb`.
Instale com `sudo apt install ./linux-iso-flasher_0.1.0-1_all.deb`.

Se você estiver no Arch/Artix ou em qualquer distro que tenha apenas
`dpkg-deb`, use o atalho que monta o `.deb` sem `debhelper`:

```sh
cd /home/miguel/linux-iso-flasher
./packaging/deb/build-deb.sh
# saída: dist/linux-iso-flasher_0.1.0-1_all.deb
```

## Fedora

```sh
sudo dnf install python3 python3-pip python3-gobject gtk4 libadwaita udisks2 \
                 polkit zstd hicolor-icon-theme
python3 -m pip install -e .
sudo systemctl restart polkit
```

O spec em `packaging/rpm/linux-iso-flasher.spec` presume um tarball local com
prefixo `linux-iso-flasher-0.1.0/`; ajuste `Source0` para o URL do seu release.

## openSUSE

```sh
sudo zypper install python311 python311-pip python3-gobject gtk4 libadwaita \
                  udisks2 polkit zstd hicolor-icon-theme
python3 -m pip install -e .
sudo systemctl restart polkitd
```

Os nomes exatos dos pacotes de typelib podem variar entre versões do openSUSE;
use `zypper search Adw` / `zypper search typelib` se algum import `gi` falhar.

## NixOS

Não há instalação tradicional em `/usr`. Use um `nix-shell`/flake com
`python311`, `gtk4`, `libadwaita`, `pygobject`, `udisks2`, `polkit` e `zstd`, e
instale o pacote em um perfil (`pip install -e . --prefix="$HOME/.local"`).
A política Polkit precisa ser disponibilizada no sistema; `security.polkit.enable
= true;` habilita o serviço, enquanto `security.polkit.extraConfig` serve para
**regras `.rules`**, não para o XML de definição da ação. Instale o `.policy`
em um diretório lido pelo polkit (normalmente
`/usr/share/polkit-1/actions/`) por meio do seu módulo/derivação.

## Instalar a política, o helper e os dados de desktop

O `pyproject.toml` instala o wrapper `packaging/helper/helper` em
`/usr/libexec/linux-iso-flasher/helper`, que é o nome exigido pela política
Polkit e pelo cliente `permissions/polkit.py`. Após `pip install` (inclusive
`-e .`), instale apenas a política e, se desejar, os dados de desktop e o
ícone:

```sh
sudo install -Dm0644 packaging/polkit/org.linuxisoflasher.pkexec.policy \
  /usr/share/polkit-1/actions/org.linuxisoflasher.pkexec.policy
sudo install -Dm0644 packaging/desktop/linux-iso-flasher.desktop \
  /usr/share/applications/linux-iso-flasher.desktop
sudo install -Dm0644 assets/icons/io.github.linuxisoflasher.svg \
  /usr/share/icons/hicolor/scalable/apps/io.github.linuxisoflasher.svg
sudo gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true
```

Os pacotes Arch/RPM desta árvore instalam todos esses arquivos
automaticamente.

Reinicie o polkit e verifique a ação e o `pkexec`:

```sh
sudo systemctl restart polkit        # em algumas distros: polkitd
pkaction --action-id org.linuxisoflasher.flash --verbose
LIF_HELPER=/usr/libexec/linux-iso-flasher/helper \
  pkexec /usr/libexec/linux-iso-flasher/helper </dev/null
```

O último comando deve solicitar a senha administrativa e responder com
`{"type": "error", "message": "Helper iniciado sem pedido."}` (saída 2): isso
confirma que o `pkexec` encontrou a política e iniciou o helper. **Não** é uma
gravação: sem a linha `start` no stdin, nenhum dispositivo é tocado.

Se o catálogo de traduções for instalado, compile e copie os `.mo` para
`/usr/share/locale/<lang>/LC_MESSAGES/linux-iso-flasher.mo`. Atualmente os
catálogos e essa etapa de instalação não fazem parte do `pyproject.toml`;
sem eles a interface permanece em pt_BR (a tradução em inglês é opcional).

## Atalhos e uso

Veja o README para o fluxo de três etapas. A interface usa os atalhos padrão
GTK4 (Tab/Shift+Tab para navegar, Enter para ativar, Esc para fechar diálogos).

## Flatpak e AppImage — aviso importante

- **Flatpak (experimental):** `pkexec` e a política Polkit do host **não**
  funcionam no sandbox padrão. O manifesto em
  `packaging/flatpak/io.github.linuxisoflasher.yaml` inclui permissões de
  D-Bus e `--talk-name=org.freedesktop.Flatpak` como ponto de partida, mas
  ainda exige uma porta/host helper (por exemplo
  `org.freedesktop.Flatpak.Development`) ou um serviço D-Bus no host. Não é
  uma via de instalação suportada na 0.1.0.
- **AppImage:** roda **fora** do sandbox, então o fluxo `pkexec` funciona
  desde que a política e o helper estejam instalados no host, como descrito
  acima. O script `packaging/appimage/build-appimage.sh` gera
  `linux-iso-flasher-x86_64.AppImage`; ele precisa de `appimagetool` e não
  redefine `LIF_HELPER` para um caminho dentro do AppImage (o ponto de
  montagem muda a cada execução e a política não casaria com o caminho).

Para gerar o AppImage, instale `python3-setuptools`, `python3-wheel` e
`appimagetool` (baixe `appimagetool-x86_64.AppImage` da página de releases do
AppImageKit e coloque-o no `PATH`), depois execute:

```sh
cd /home/miguel/linux-iso-flasher
./packaging/appimage/build-appimage.sh
```

Use `APPIMAGE_TOOL=/caminho/appimagetool` se o binário não estiver no `PATH` e
`PYTHON=/caminho/do/python` se o `python3` do sistema não tiver `setuptools`
instalado (por exemplo, ao usar um virtualenv).
O arquivo `linux-iso-flasher-x86_64.AppImage` é criado na raiz do projeto.
Em distribuições sem FUSE 2, rode com
`APPIMAGE_EXTRACT_AND_RUN=1 ./linux-iso-flasher-x86_64.AppImage` ou instale
`libfuse2`.

## Desinstalação (instalação manual)

```sh
sudo rm -f /usr/libexec/linux-iso-flasher/helper \
           /usr/share/polkit-1/actions/org.linuxisoflasher.pkexec.policy \
           /usr/share/applications/linux-iso-flasher.desktop \
           /usr/share/icons/hicolor/scalable/apps/io.github.linuxisoflasher.svg
python3 -m pip uninstall linux-iso-flasher
```
