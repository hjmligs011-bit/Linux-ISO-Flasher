# Arquitetura — Linux ISO Flasher 0.1.0

## Visão geral

A aplicação separa rigorosamente a interface (usuário) da única parte que pode
escrever em dispositivos de bloco (helper root). Toda decisão de segurança é
revalidada no helper; a GUI nunca monta linhas de comando e nunca roda como root.

```
GTK4/libadwaita (ui)
   |  seleção de imagem + dispositivo
   v
core/models (ImageInfo, DeviceInfo, DeviceIdentity)
   |
   +--> images/  (detector + reader em fluxo)
   +--> devices/ (UDisks2 + sysfs)
   |
   v
permissions/polkit.py -- JSON-lines --> pkexec --> helper (root)
                      <-- progress/result/error <--
                                        |
                                        v
                          flashing/engine.py -> FlashTarget
```

## Módulos

- `core/` — `models.py` (modelos imutáveis: `ImageInfo`, `DeviceInfo`,
  `DeviceIdentity`, `PartitionInfo`, `FlashProgress`, `FlashResult`,
  `HistoryEntry`), `config.py` (configuração XDG em `config.json`), `errors.py`
  (hierarquia `FlasherError`), `i18n.py` (gettext, pt_BR padrão e en).
- `devices/` — `sysfs.py` lê atributos reais de `/sys/block`, valida o nome do
  dispositivo contra path traversal e identifica dispositivos do sistema pelos
  pares major:minor de pontos de montagem críticos; `udisks.py` usa
  `Gio.DBusConnection` no barramento do sistema para `GetManagedObjects`,
  `GetBlockDevices`, assinaturas de mudanças e `Filesystem.Unmount`;
  `manager.py` é a fachada observável usada pela interface.
- `images/` — `detector.py` confirma o formato por assinatura de bytes
  (`magic numbers`) e extensão e estima o tamanho descomprimido; `reader.py`
  entrega chunks de 1 MiB para imagens cruas, xz, gzip e zstd, sem carregar a
  imagem inteira em memória.
- `flashing/` — `targets.py` define `FlashTarget`, `FileTarget` (testes) e
  `BlockDeviceTarget` (único destino real) além de `assert_safe_target()`;
  `engine.py` (`FlashController`) executa escrita e `fsync`;
  `helper.py` valida o pedido, impõe as regras de segurança e fala JSON-lines;
  `helper_entry.py` é o ponto de entrada usado a partir do repositório. O
  wrapper instalado como `/usr/libexec/linux-iso-flasher/helper` está em
  `packaging/helper/helper`.
- `verification/` — `verifier.py` (`IntegrityVerifier`) reabre a imagem,
  compara cada chunk com a leitura do dispositivo e gera o SHA-256 verificado.
- `permissions/` — `polkit.py` (`HelperLauncher`) localiza o helper
  (`LIF_HELPER`, `/usr/libexec/linux-iso-flasher/helper`, cópia do repositório),
  invoca `pkexec`, envia `start`/`cancel` e converte eventos em progresso,
  resultado ou erro da aplicação.
- `history/` — `store.py` salva apenas metadados em
  `$XDG_STATE_HOME/linux-iso-flasher/history.json`, com escrita atômica
  (`tmp` + `os.replace`) e limite configurável.
- `utils/` — formatação de tamanho/tempo e logging.
- `ui/` — camada GTK4/libadwaita: escolha de imagem, lista de dispositivos,
  confirmação, progresso, cancelamento e histórico. Ela consome os modelos e o
  `HelperLauncher`; não contém lógica de escrita em bloco.

## Fluxo de dados

1. A GUI usa `images.detector.inspect_image()` e `devices.manager` para montar
   `ImageInfo` e `DeviceInfo`; discos internos e partições nunca aparecem como
   alvo.
2. O usuário confirma a operação; a GUI envia ao helper um JSON com
   `image_path`, `target_sysname`, `expected_fingerprint`, `chunk_size` e
   `verify`.
3. `HelperLauncher` inicia `pkexec /usr/libexec/linux-iso-flasher/helper`; o
   Polkit aplica a ação `org.linuxisoflasher.flash`
   (`auth_admin_keep` para sessão ativa; `auth_admin` para as demais).
4. O helper valida o pedido, revalida a imagem e o dispositivo, desmonta
   partições via UDisks2 e chama `FlashController.run()` com
   `BlockDeviceTarget`.
5. Eventos `progress` são enviados em JSON-lines e atualizam a barra da GUI;
   ao final, `result` (ou `error`) encerra a operação e alimenta o histórico.
6. `cancel` pode ser enviado pela GUI ou gerado por SIGINT/SIGTERM; o
   `FlashController` verifica o `threading.Event` entre chunks.

## Modelo de segurança

- **Origem dos dados:** todos os atributos vêm de sysfs ou UDisks2; nomes de
  dispositivo passam por `validate_sysname()` antes de montar caminhos.
- **Fingerprint:** SHA-256 de `vendor`, `model`, `serial`, `size`, `transport` e
  `media`. Ele é calculado na seleção e recalculado logo antes da primeira
  escrita (`verify_identity()`); divergência aborta a gravação.
- **Bloqueio de discos internos:** `assert_safe_target()` exige dispositivo
  inteiro (não partição), `removable` ou transporte USB/card típico, capacidade
  válida, ausência de montagens do sistema (`/`, `/boot`, `/boot/efi`, `/usr`,
  `/var`, `/etc`, `/home`) e `stat.S_ISBLK` com major/minor conferidos.
- **Desmontagem:** feita via `UDisks2.Filesystem.Unmount` (com `force`) antes
  da abertura do descritor; falha impede a gravação.
- **Escrita:** `os.open(..., O_WRONLY | O_SYNC)` e `os.pwrite` com verificação
  de contagem de bytes; leitura de verificação usa descritor separado
  `O_RDONLY`. Nenhum comando de shell é construído a partir de dados do
  dispositivo. A única exceção é a descompressão zstd via lista de argumentos
  (`subprocess.Popen([...])`, sem `shell=True`).
- **Privilégio mínimo:** a GUI e o gerenciador de dispositivos rodam como
  usuário; somente o helper, com Polkit, escreve no dispositivo.

## Protocolo JSON (JSON-lines, UTF-8)

Pedido (GUI → helper, uma linha):

```json
{"type": "start", "request": {
  "image_path": "/caminho/absoluto/imagem.iso",
  "target_sysname": "sdb",
  "expected_fingerprint": "<64 hex>",
  "chunk_size": 1048576,
  "verify": true
}}
```

Durante a operação:

```json
{"type": "progress", "stage": "write|verify|prepare|finish",
 "done": 0, "total": 0, "speed": 0.0, "eta": null, "message": "..."}
```

Encerramento:

```json
{"type": "result", "success": true, "result": {
  "success": true, "verified": true, "cancelled": false,
  "bytes_written": 0, "duration": 0.0, "sha256": null, "error": null,
  "image": {}, "device": {}
}}
{"type": "error", "message": "descrição tratável"}
{"type": "cancel"}
```

O `cancel` é enviado pelo cliente; o helper também reage a sinais. O cliente
ainda trata `auth_failed` como erro de permissão (o helper atual não emite
esse tipo; é uma defesa adicional no protocolo). Códigos de saída do helper:
`0` sucesso, `1` resultado com falha, `2` pedido inválido, `3` erro tratável,
`4` erro inesperado.

## Verificação

Implementada em `verification/verifier.py` (`IntegrityVerifier`): após a
passagem de escrita e `fsync`, o motor relê o destino em chunks, compara byte a
byte com a imagem descomprimida e calcula SHA-256 tanto do fluxo de entrada
quanto do fluxo lido. Divergência gera `VerificationError`. Na versão 0.1.0,
`FlashController` preenche `success = verified` — portanto, com `verify=False`,
uma gravação sem erros ainda aparece como `success=False`; use essa opção apenas
para depuração.

## Decisões de tecnologia

- **GTK4 + libadwaita via PyGObject:** integração nativa ao desktop GNOME e a
  outros ambientes Wayland/X11, sem toolkit próprio.
- **Python 3.11+:** streaming com `lzma`/`gzip` da biblioteca padrão e
  tipagem moderna; `compression.zstd` é usado quando disponível.
- **UDisks2 em vez de comandos shell:** enumeração e desmontagem passam pela
  API D-Bus oficial, com assinaturas para refletir plug/replug.
- **Sem root na GUI:** Polkit + helper isolado reduzem a superfície de ataque;
  a política pede senha (`auth_admin`) e mantém a autorização por sessão.
- **Persistência XDG:** configuração em `$XDG_CONFIG_HOME`, histórico em
  `$XDG_STATE_HOME`; nenhum dado de imagem é copiado para o histórico.

Fora de escopo na 0.1.0: catálogo de downloads, comparação com checksum
fornecido pelo usuário (o SHA-256 calculado é apenas interno), suporte a ISO
híbrida e traduções além de pt_BR/en.
