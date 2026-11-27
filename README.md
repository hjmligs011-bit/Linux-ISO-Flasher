# Linux ISO Flasher

[![version](https://img.shields.io/badge/version-0.1.0-blue)](https://github.com/linux-iso-flasher/linux-iso-flasher/releases)
[![license](https://img.shields.io/badge/license-GPL--3.0--or--later-green)](LICENSE)
[![platform](https://img.shields.io/badge/platform-Linux-orange?logo=linux)](#instalação)
[![UI](https://img.shields.io/badge/UI-GTK4%20%2B%20libadwaita-purple)](#visão-geral)

Gravador nativo de imagens para dispositivos removíveis em Linux. A interface
GTK4/libadwaita roda como **usuário comum**; toda escrita em dispositivo de bloco
acontece em um **helper privilegiado**, autorizado pelo Polkit e verificado byte
a byte ao final.

Inspirado na simplicidade do Balena Etcher, com identidade própria, integração
nativa ao desktop e foco em segurança. **Linux apenas**: Arch, Debian/Ubuntu,
Fedora, openSUSE, Mint e NixOS; GNOME, KDE, XFCE, Hyprland e Sway, em Wayland ou
X11.

> **Versão 0.1.0** — primeira versão estável de gravação. Catálogo de downloads,
> checksum informado pelo usuário, ISO híbrida e idiomas além de pt_BR/en ficam
> para uma próxima versão.

---

## Visão geral

O fluxo foi desenhado em três etapas curtas e explícitas:

1. **Selecionar imagem** — por botão ou arrastando o arquivo para a janela.
2. **Selecionar dispositivo** — apenas mídias removíveis detectadas via UDisks2.
3. **Gravar** — confirmação de apagamento, autenticação Polkit, progresso,
   verificação e registro no histórico.

A aplicação não executa comandos de shell construídos a partir de dados do
usuário, não monta discos por conta própria e nunca reporta sucesso sem a
verificação ter passado.

---

## Capturas de tela

> Espaço reservado para as capturas. Os arquivos ainda não estão incluídos no
> repositório; veja [`docs/screenshots/README.md`](docs/screenshots/README.md)
> para nomes, dimensionamento e comandos de captura.

| Etapa | Captura sugerida |
| --- | --- |
| Janela principal | `docs/screenshots/01-inicio.png` |
| Imagem selecionada | `docs/screenshots/02-imagem-selecionada.png` |
| Dispositivos detectados | `docs/screenshots/03-dispositivos.png` |
| Confirmação de apagamento | `docs/screenshots/04-confirmacao.png` |
| Gravação e verificação | `docs/screenshots/05-progresso.png` |
| Resultado verificado | `docs/screenshots/06-resultado.png` |
| Histórico | `docs/screenshots/07-historico.png` |
| Preferências | `docs/screenshots/08-preferencias.png` |

Modelo para preencher a tabela acima quando as imagens existirem:

```markdown
| Janela principal | ![Janela principal](docs/screenshots/01-inicio.png) |
| Gravação e verificação | ![Progresso](docs/screenshots/05-progresso.png) |
| Resultado verificado | ![Sucesso](docs/screenshots/06-resultado.png) |
```

---

## Principais recursos

### Fluxo e interface

- Três etapas visuais com cards numerados, tema escuro padrão e tema claro
  opcional, paleta Catppuccin Mocha e animações discretas.
- Seletor de arquivos com filtros e **drag-and-drop**.
- Lista de dispositivos com modelo, fabricante, capacidade, caminho,
  transporte, partições e espaço disponível.
- Atualização automática na inserção/remoção de mídia via sinais UDisks2, com
  polling leve de 3 segundos como fallback.
- Progresso com porcentagem, dados gravados, velocidade, ETA e estágio atual
  (`prepare`, `write`, `verify`, `finish`).
- Cancelamento seguro entre chunks, com resultado registrado como cancelado.

### Segurança por design

- A GUI nunca roda como root. `pkexec` inicia somente
  `/usr/libexec/linux-iso-flasher/helper`, usando a ação Polkit
  `org.linuxisoflasher.flash` com `auth_admin_keep` na sessão ativa e sem
  `allow_yes`.
- Protocolo JSON-lines com mensagens `start`, `progress`, `result`, `error` e
  `cancel`. Nenhum comando de shell é montado a partir de entrada externa.
- O helper valida estritamente o pedido: caminho absoluto da imagem, `sysname`
  seguro, fingerprint SHA-256 com 64 hex, `chunk_size` entre 64 KiB e 16 MiB e
  `verify` booleano.
- Discos internos, partições e dispositivos com montagens do sistema são
  bloqueados. As partições removíveis são desmontadas via UDisks2 antes da
  escrita.
- A identidade do dispositivo (vendor, model, serial, tamanho, transporte e
  mídia) é recalculada pelo helper imediatamente antes da primeira escrita.
  Trocar a mídia ou a porta aborta a operação.
- `fsync` ao final e verificação obrigatória: comparação byte a byte em chunks e
  SHA-256 da imagem e do dispositivo. `FlashResult.success` só é `True` quando
  `verified` também é.

### Dados locais

- Configuração em `$XDG_CONFIG_HOME/linux-iso-flasher/config.json`: tema
  (`dark`, `light`, `system`), idioma (`pt_BR`, `en`), tamanho de chunk, limite
  do histórico e último diretório usado.
- Histórico em `$XDG_STATE_HOME/linux-iso-flasher/history.json`, escrito de
  forma atômica, limitado por configuração e consultável/limpável na interface.
  Guarda apenas metadados — nunca copia dados da imagem.

---

## Formatos suportados

| Entrada | Manipulação |
| --- | --- |
| `.iso`, `.img`, `.raw`, `.bin` | fluxo direto |
| `.xz`, `.gz` | descompressão com a biblioteca padrão |
| `.zst` | `compression.zstd` quando disponível; senão binário `zstd` |

A detecção usa **assinatura de bytes**, não apenas a extensão. Imagens
comprimidas de até 512 MiB são varridas por completo antes da gravação para
detectar corrupção e obter o tamanho exato após descompressão. A leitura é
feita em fluxo, sem carregar o arquivo inteiro em memória.

---

## Requisitos

### Para executar

- Linux com Python 3.11+, GTK 4, libadwaita e PyGObject.
- UDisks2 para enumeração e desmontagem.
- Polkit e `pkexec` para autorização do helper.
- `hicolor-icon-theme` para o ícone.
- `zstd` apenas se o Python não oferecer `compression.zstd`.

Pacotes por distribuição em [`docs/INSTALL.md`](docs/INSTALL.md).

### Para compilar/testar

- `setuptools`, `wheel` e `build` para gerar o wheel.
- `unittest` da biblioteca padrão para os testes.
- `xgettext`, `msgfmt` e `msgmerge` apenas para atualizar traduções.
- `appimagetool` para o AppImage; `dpkg-deb` para o `.deb`.

---

## Instalação

Escolha o método da sua distribuição. Os pacotes nativos instalam o helper, a
política Polkit, o `.desktop`, o ícone e os catálogos de idioma. O AppImage
depende do helper e da política já instalados no host.

### Arch Linux / Artix — AUR

```sh
yay -S linux-iso-flasher
# ou
paru -S linux-iso-flasher
```

O `PKGBUILD` e o `.SRCINFO` prontos para publicação estão em
[`packaging/aur/`](packaging/aur/).

### Arch Linux / Artix — pacote local

```sh
sudo pacman -U linux-iso-flasher-0.1.0-1-any.pkg.tar.zst
```

Ou compile a partir do código:

```sh
cd packaging/arch
makepkg -si
```

### Debian / Ubuntu

```sh
sudo apt install ./linux-iso-flasher_0.1.0-1_all.deb
```

Para gerar o `.deb` sem `debhelper` (funciona até no Artix):

```sh
./packaging/deb/build-deb.sh
# saída: dist/linux-iso-flasher_0.1.0-1_all.deb
```

### Fedora / RHEL-like

```sh
sudo dnf install ./linux-iso-flasher-0.1.0-1*.noarch.rpm
```

O spec está em [`packaging/rpm/`](packaging/rpm/).

### AppImage

```sh
chmod +x linux-iso-flasher-x86_64.AppImage
./linux-iso-flasher-x86_64.AppImage
```

Em sistemas sem FUSE 2:

```sh
APPIMAGE_EXTRACT_AND_RUN=1 ./linux-iso-flasher-x86_64.AppImage
```

O AppImage roda fora do sandbox, mas ainda depende do helper e da política
Polkit instalados no host.

### Flatpak (experimental)

O manifesto em [`packaging/flatpak/`](packaging/flatpak/) é referência apenas.
O sandbox padrão não permite `pkexec`/Polkit do host, então é necessária uma
porta D-Bus ou um serviço host separado. **Não é a via suportada na 0.1.0.**

### Direto do repositório

```sh
git clone https://github.com/linux-iso-flasher/linux-iso-flasher.git
cd linux-iso-flasher
PYTHONPATH=src python3 -m linux_iso_flasher.main
```

Para testar a integração com `pkexec` sem instalar, defina:

```sh
export LIF_HELPER="$PWD/src/linux_iso_flasher/flashing/helper_entry.py"
```

---

## Uso

1. Abra o aplicativo e clique em **Selecionar imagem** ou arraste o arquivo.
2. Conecte o pendrive/cartão e selecione-o na lista. Confira caminho, modelo e
   capacidade; **todos os dados do destino serão apagados**.
3. Leia a confirmação, marque o checkbox e clique em **Gravar agora**.
4. Autentique no diálogo do Polkit e acompanhe gravação e verificação.
5. Não remova a mídia até a tela de resultado aparecer.

O botão **Cancelar** interrompe a operação entre chunks. O dispositivo pode
ficar parcialmente gravado; o evento aparece no histórico como cancelado.

### Atalhos

| Tecla | Ação |
| --- | --- |
| `Tab` / `Shift+Tab` | navegar pelos controles |
| `Enter` | ativar o controle focado |
| `Esc` | fechar diálogos |
| `Ctrl+Q` | sair do aplicativo |

O helper trata `SIGINT`/`SIGTERM` como cancelamento.

### Solução de problemas

| Sintoma | Causa provável | Ação |
| --- | --- | --- |
| Nenhum dispositivo aparece | mídia interna ou ainda não detectada | conecte novamente e clique em **Atualizar**; discos internos são bloqueados por segurança |
| `Polkit não autorizou` | autenticação cancelada ou política não instalada | verifique `/usr/share/polkit-1/actions/org.linuxisoflasher.pkexec.policy` e reinicie o polkit |
| `Helper privilegiado não encontrado` | helper fora do caminho padrão | instale o pacote ou defina `LIF_HELPER` |
| `.zst` rejeitado | sem `compression.zstd` e sem `zstd` | instale `zstd` |
| AppImage não abre | FUSE 2 ausente | instale `libfuse2` ou use `APPIMAGE_EXTRACT_AND_RUN=1` |
| Verificação falhou | mídia defeituosa, troca de dispositivo ou dados divergentes | não use a mídia; repita com outro dispositivo |

---

## Empacotamento e releases

Os artefatos de release são gerados em `dist/`:

| Artefato | Uso |
| --- | --- |
| `linux-iso-flasher_0.1.0-1_all.deb` | Debian/Ubuntu |
| `linux-iso-flasher-0.1.0-1-any.pkg.tar.zst` | Arch/Artix |
| `linux-iso-flasher-x86_64.AppImage` | distribuições com FUSE 2 |
| `linux-iso-flasher-0.1.0.tar.gz` | fonte para o AUR/GitHub Release |
| `SHA256SUMS` | conferência dos arquivos acima |

Comandos de geração:

```sh
./packaging/deb/build-deb.sh
PYTHON=/caminho/do/python ./packaging/appimage/build-appimage.sh
cd packaging/aur && makepkg --nodeps
cd dist && sha256sum linux-iso-flasher-* > SHA256SUMS
```

Detalhes completos em [`docs/INSTALL.md`](docs/INSTALL.md).

---

## Documentação

| Documento | Conteúdo |
| --- | --- |
| [`docs/INSTALL.md`](docs/INSTALL.md) | instalação, dependências, empacotamento e desinstalação |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | módulos, protocolo do helper, decisões de segurança |
| [`docs/TESTING.md`](docs/TESTING.md) | execução da suíte, regras e smoke test da UI |
| [`docs/screenshots/README.md`](docs/screenshots/README.md) | espaço e nomenclatura das capturas |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | como contribuir e padrões de código |
| [`po/`](po/) | catálogos gettext pt_BR/en e modelo `.pot` |
| [`LICENSE`](LICENSE) | texto completo da GPL-3.0-or-later |

---

## Estrutura do projeto

```text
linux-iso-flasher/
├── src/linux_iso_flasher/
│   ├── core/           modelos, configuração, i18n e erros
│   ├── devices/        sysfs, UDisks2 e gerenciador de dispositivos
│   ├── flashing/       targets, motor de gravação e helper privilegiado
│   ├── verification/   verificador de integridade pós-gravação
│   ├── images/         detecção e leitura em fluxo (xz/gz/zst)
│   ├── permissions/    cliente pkexec/Polkit
│   ├── history/        histórico atômico em XDG_STATE_HOME
│   ├── ui/             janela, diálogos, CSS e aplicação Adwaita
│   ├── locale/         catálogos .mo incluídos no pacote
│   └── main.py         ponto de entrada da interface
├── tests/              testes com FileTarget e smoke test da UI
├── packaging/          Arch, AUR, deb, RPM, Flatpak, AppImage e Polkit
├── docs/               instalação, arquitetura, testes e capturas
├── po/                 traduções
├── tools/              atualização dos catálogos gettext
└── pyproject.toml      build, entry point e data-files
```

---

## Desenvolvimento

```sh
# Testes automatizados (somente arquivos temporários; nenhum disco real)
PYTHONPATH=src python3 -m unittest discover -s tests -v

# Smoke test da interface com helper falso e dispositivo sintético
PYTHONPATH=src python3 tests/smoke_ui.py

# Executar a aplicação
PYTHONPATH=src python3 -m linux_iso_flasher.main

# Wheel
python3 -m build --wheel

# Traduções
./tools/update-translations.sh
```

**Regra absoluta:** os testes nunca instanciam `BlockDeviceTarget` com disco
real, nunca chamam `pkexec` e nunca escrevem em `/dev/*`. Use `FileTarget` e
`tempfile.TemporaryDirectory()`.

Mensagens novas seguem pt_BR como idioma-fonte e passam por `tr()`/`_()`;
depois rode `./tools/update-translations.sh` e traduza o `en.po`.

---

## Estado do projeto e limitações

Implementado na 0.1.0: gravação verificada, cancelamento, UDisks2, Polkit,
histórico, i18n pt_BR/en, tema escuro/claro e pacotes para Arch/AUR, deb, RPM,
AppImage e Flatpak experimental.

Ainda não implementado: catálogo de downloads, comparação com checksum digitado
pelo usuário, suporte a ISO híbrida e idiomas além de pt_BR/en.

Não há capturas de tela versionadas neste momento — o espaço está preparado em
[`docs/screenshots/`](docs/screenshots/).

---

## Contribuindo

Contribuições são bem-vindas. Antes de abrir um PR, leia
[`CONTRIBUTING.md`](CONTRIBUTING.md) e [`docs/TESTING.md`](docs/TESTING.md),
rode os testes e o smoke test e mantenha pt_BR como idioma-fonte das strings.

---

## Licença

GPL-3.0-or-later. Texto completo em [`LICENSE`](LICENSE).
