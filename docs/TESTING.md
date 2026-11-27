# Testes — Linux ISO Flasher 0.1.0

## Executando a suíte

```sh
# Sem instalação editável, a partir da raiz do repositório:
PYTHONPATH=src python -m unittest discover -s tests -v

# Com `python -m pip install -e .`:
python -m unittest discover -s tests -v

# Um arquivo específico:
python -m unittest tests.test_flashing -v
```

A suíte usa apenas `unittest` da biblioteca padrão (`[project.optional-dependencies]
test = []`). Nenhum dispositivo de bloco, serviço do sistema ou arquivo fora de
um diretório temporário é necessário.

## Regra absoluta: nunca gravar discos reais em testes

- Use **`FileTarget`** (`flashing/targets.py`) com arquivos criados em
  `tempfile.TemporaryDirectory()`.
- **Nunca** instancie `BlockDeviceTarget` em testes automáticos e nunca passe
  `/dev/sdX`, `/dev/mmcblkX` ou qualquer `sysname` real para o helper.
- Não chame `pkexec` em testes automáticos. Testes de autorização Polkit são
  manuais e devem ser feitos apenas com mídia removível descartável.
- Não use `identity_from_sysfs()` com nomes reais em testes de unidade; para
  testar validação de identidade, construa `DeviceIdentity` diretamente.

## Padrão recomendado (motor + FileTarget)

Crie uma imagem temporária e um arquivo-alvo com o mesmo tamanho, pois
`FileTarget` calcula a capacidade com `stat()` no construtor:

```python
import tempfile
import unittest
from pathlib import Path

from linux_iso_flasher.core.models import ImageInfo
from linux_iso_flasher.flashing.engine import FlashController
from linux_iso_flasher.flashing.targets import FileTarget


class TestFlashController(unittest.TestCase):
    def test_write_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = b"conteudo generico de exemplo" * 32
            image = Path(tmp) / "prova.iso"
            image.write_bytes(payload)

            destination = Path(tmp) / "alvo.img"
            with destination.open("wb") as handle:
                handle.truncate(len(payload))

            info = ImageInfo(
                path=image, size=len(payload), fmt="iso",
                container=None, uncompressed_size=len(payload),
            )
            target = FileTarget(destination)
            result = FlashController(info, target, verify=True).run()

            self.assertTrue(result.success)
            self.assertTrue(result.verified)
            self.assertEqual(destination.read_bytes(), payload)
```

Também é útil cobrir: cancelamento com `threading.Event`, imagem maior que o
alvo (`ImageTooLargeError` encapsulado em `FlashResult.error`), imagem vazia e
divergência de verificação. Use `on_progress` para coletar os eventos
`write`/`verify`/`finish` e conferir os estágios.

Para imagens comprimidas, gere o arquivo com `lzma.open()`/`gzip.open()` no
próprio teste e use `images.detector.inspect_image()` para obter o `ImageInfo`
real — o `reader` descomprime em fluxo e o motor grava o conteúdo descomprimido.
O caso zstd depende da disponibilidade de `compression.zstd` ou do binário
`zstd`; pule o teste quando nenhum dos dois existir.

## Testando o helper e o cliente de permissões

`LIF_HELPER` é lido por `permissions/polkit.py:helper_candidates()` e substitui
o caminho padrão do helper. Ele **não cria sandbox**: se apontar para o helper
real, uma solicitação válida gravará um dispositivo de verdade. Por isso:

1. **Testes puros do helper:** importe `validate_request()` e `emit()` e
   verifique validação de tipos, caminho absoluto da imagem, `sysname`,
   fingerprint de 64 hex e limites de `chunk_size`. Você também pode chamar
   `run_helper()` com uma linha inválida no stdin e confirmar `{"type":
   "error"}` e código `2`; isso não toca em dispositivo algum.
2. **Testes do protocolo do launcher:** crie, dentro do diretório temporário,
   um executável de teste que leia uma linha do stdin e escreva linhas
   `progress` e `result` no stdout. Em seguida use:
   `HelperLauncher(helper_path=caminho_do_teste, use_pkexec=False)`. Isso
   exercita parsing, progresso, resultado e cancelamento sem root e sem
   dispositivos.
3. **Fluxo completo de gravação:** use `FlashController` + `FileTarget` como no
   exemplo acima. O helper real sempre usa `BlockDeviceTarget`; ele não aceita
   um arquivo temporário como destino e, portanto, não deve ser usado nesse
   teste.

Exemplo de execução manual do helper **sem pedido válido** (seguro):

```sh
LIF_HELPER=/usr/libexec/linux-iso-flasher/helper \
  python -c 'from linux_iso_flasher.flashing.helper_entry import run_helper; raise SystemExit(run_helper())' \
  </dev/null
```

Saída esperada: `{"type": "error", "message": "Helper iniciado sem pedido."}`
e código `2`. Para testar `pkexec` de verdade, reinicie o polkit e siga
`docs/INSTALL.md`; use apenas mídia removível que possa ser apagada.

## Smoke test da interface

O arquivo `tests/smoke_ui.py` exercita a janela real com um helper falso e um
dispositivo sintético em memória: nenhum arquivo de bloco é tocado.

```sh
PYTHONPATH=src python3 tests/smoke_ui.py
```

A saída esperada termina em `SMOKE OK`. Ele é útil para detectar regressões em
GTK4/libadwaita sem exigir interação ou mídia removível.

## Traduções

Após alterar strings visíveis ao usuário, regenere e compile os catálogos:

```sh
./tools/update-translations.sh
```

O comando atualiza `po/linux-iso-flasher.pot`, mescla as mudanças em `po/*.po`
e gera os arquivos `.mo` incluídos no pacote.

## Checklist antes de enviar mudanças

- [ ] `python -m unittest discover -s tests -v` passa sem root.
- [ ] Nenhum teste grava em `/dev/*`, instancia `BlockDeviceTarget` com
  dispositivo real ou chama `pkexec` (strings `/dev/...` em modelos/validação
  são aceitáveis, desde que não haja abertura ou escrita).
- [ ] Mudanças em `flashing/`, `devices/` ou `permissions/` têm teste novo.
- [ ] Mensagens novas seguem pt_BR como idioma-fonte e passam por `tr()`/`_()`.
